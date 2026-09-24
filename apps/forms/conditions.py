from graphlib import CycleError, TopologicalSorter

from django.core.exceptions import ValidationError

from .additional_choices import additional_text_config
from .dependent_choices import option_filters
from .public_fields import CHOICE_TYPES, DISPLAY_TYPES, TEXT_TYPES, empty, json_value, public_field
from .question_fields import FILE_TYPES, GRID_TYPES, SCALE_TYPES


class FormSchema:
    def __init__(self, version):
        self.version = version
        self.sections = list(version.sections.order_by("order", "id"))
        self.fields = list(
            version.fields.select_related("section", "image")
            .prefetch_related("options__image")
            .order_by("section__order", "section_id", "order", "id")
        )
        self.by_id = {str(field.pk): field for field in self.fields}
        self.section_ids = [str(section.pk) for section in self.sections]
        self.navigation = {}
        navigation_graph = {}
        for index, section in enumerate(self.sections):
            key = str(section.pk)
            following = self.section_ids[index + 1] if index + 1 < len(self.sections) else None
            destination = section.configuration.get("next_section", "NEXT")
            if not isinstance(destination, str) or destination not in {
                "NEXT",
                "SUBMIT",
                *self.section_ids,
            }:
                raise ValidationError(f"Revisa el destino de la sección «{section.title}».")
            target = (
                following
                if destination == "NEXT"
                else (None if destination == "SUBMIT" else destination)
            )
            self.navigation[key] = {"next": target, "following": following}
            navigation_graph[key] = {target} if target else set()
        if any(field.section.form_version_id != version.pk for field in self.fields):
            raise ValidationError("Todos los campos deben pertenecer a secciones de esta versión.")
        self.inputs = {str(field.pk): public_field(field) for field in self.fields}
        self.option_filters = option_filters(self.fields)
        self.groups = []
        grouped = {}
        for rule in version.rules.order_by("order", "id"):
            if rule.action not in {
                "SHOW",
                "HIDE",
                "REQUIRE",
                "OPTIONAL",
            } or rule.group_operator not in {"AND", "OR"}:
                raise ValidationError("Acción u operador de grupo no admitido.")
            key = f"group:{rule.group_key}" if rule.group_key else str(rule.pk)
            source = self.by_id.get(str(rule.source_field_id))
            if source is None or source.field_type in DISPLAY_TYPES:
                raise ValidationError(
                    "Las condiciones deben usar campos con respuesta de esta versión."
                )
            targets = (
                [str(rule.target_field_id)]
                if rule.target_field_id
                else [
                    str(field.pk)
                    for field in self.fields
                    if field.section_id == rule.target_section_id
                ]
            )
            if not targets or any(target not in self.by_id for target in targets):
                raise ValidationError("Revisa el destino de las condiciones.")
            if key not in grouped:
                grouped[key] = {
                    "action": rule.action,
                    "operator": rule.group_operator,
                    "targets": targets,
                    "scope": "field" if rule.target_field_id else "section",
                    "conditions": [],
                }
                self.groups.append(grouped[key])
            group = grouped[key]
            if (group["action"], group["operator"], group["targets"]) != (
                rule.action,
                rule.group_operator,
                targets,
            ):
                raise ValidationError("Cada grupo debe compartir acción, operador y destino.")
            expected = self.expected_value(source, rule)
            group["conditions"].append(
                {"source": str(source.pk), "operator": rule.operator, "expected": expected}
            )
        dependencies = {key: set() for key in self.by_id}
        for key, config in self.option_filters.items():
            dependencies[key].add(config["source"])
        # A section whose every card can be hidden may also take its fallback edge.
        for section_id, navigation in self.navigation.items():
            keys = [key for key, field in self.by_id.items() if str(field.section_id) == section_id]
            can_skip = keys and all(
                any(
                    key in group["targets"] and group["action"] in {"SHOW", "HIDE"}
                    for group in self.groups
                )
                for key in keys
            )
            if can_skip and navigation["following"]:
                navigation_graph[section_id].add(navigation["following"])
        try:
            list(TopologicalSorter(navigation_graph).static_order())
        except CycleError as error:
            raise ValidationError(
                "La navegación entre secciones forma un ciclo. Elige otro destino "
                "o «Enviar formulario» para que la persona pueda terminar."
            ) from error
        for group in self.groups:
            for target in group["targets"]:
                dependencies[target].update(
                    condition["source"] for condition in group["conditions"]
                )
        try:
            self.order = list(TopologicalSorter(dependencies).static_order())
        except CycleError as error:
            raise ValidationError(
                "Las condiciones forman un ciclo; corrígelo antes de publicar."
            ) from error

    def expected_value(self, source, rule):
        operator = rule.operator
        expected = rule.expected_value
        if operator in {"IS_EMPTY", "IS_NOT_EMPTY"}:
            return None
        if source.field_type in FILE_TYPES | GRID_TYPES:
            raise ValidationError("En archivos y cuadrículas usa «Está vacío» o «No está vacío».")
        if operator in {"GREATER_THAN", "LESS_THAN"}:
            if source.field_type not in {"NUMBER", *SCALE_TYPES} or empty(expected):
                raise ValidationError(
                    "Mayor/menor que necesita un campo numérico y un valor de comparación."
                )
        if operator == "CONTAINS":
            if source.field_type not in TEXT_TYPES | CHOICE_TYPES or not isinstance(expected, str):
                raise ValidationError("Contiene necesita un texto o una opción de selección.")
            return expected
        if operator not in {"EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN"}:
            raise ValidationError("Operador condicional no soportado.")
        if source.field_type == "BOOLEAN":
            if not isinstance(expected, bool):
                raise ValidationError("Las condiciones Sí/No deben usar true o false en JSON.")
            return expected
        try:
            return json_value(self.inputs[str(source.pk)].clean(expected))
        except (ValidationError, TypeError, ValueError) as error:
            raise ValidationError(
                f"Valor esperado inválido en una condición de «{source.label}»."
            ) from error

    def states(self, values, allowed_sections=None):
        values = dict(values)
        states = {}
        for key in self.order:
            groups = [group for group in self.groups if key in group["targets"]]
            visibility = {
                scope: not any(
                    group["action"] == "SHOW" and group["scope"] == scope for group in groups
                )
                for scope in ("field", "section")
            }
            required = self.by_id[key].required
            for group in groups:
                results = []
                for condition in group["conditions"]:
                    source = condition["source"]
                    results.append(
                        states[source]["visible"]
                        and compare(
                            values.get(source), condition["operator"], condition["expected"]
                        )
                    )
                matched = all(results) if group["operator"] == "AND" else any(results)
                if matched:
                    match group["action"]:
                        case "SHOW":
                            visibility[group["scope"]] = True
                        case "HIDE":
                            visibility[group["scope"]] = False
                        case "REQUIRE":
                            required = True
                        case "OPTIONAL":
                            required = False
            visible = all(visibility.values())
            if allowed_sections is not None:
                visible = visible and str(self.by_id[key].section_id) in allowed_sections
            available = True
            if config := self.option_filters.get(key):
                source = config["source"]
                parent = values.get(source)
                available = states[source]["visible"] and not empty(parent)
                selected = values.get(key)
                if not available or parent not in config["values"].get(selected, []):
                    values[key] = None
            states[key] = {
                "visible": visible,
                "required": visible and available and required,
                "available": available,
            }
        return states

    def journey(self, values):
        """Resolve the same section path on the server and in the public form."""
        path = []
        current = self.section_ids[0] if self.section_ids else None
        while current:
            states = self.states(values, {*path, current})
            keys = [key for key, field in self.by_id.items() if str(field.section_id) == current]
            visible = not keys or any(states[key]["visible"] for key in keys)
            if visible:
                path.append(current)
            current = self.navigation[current]["next" if visible else "following"]
        return path, self.states(values, set(path))

    def browser_spec(self):
        return {
            "sections": self.section_ids,
            "navigation": self.navigation,
            "order": self.order,
            "groups": self.groups,
            "fields": {
                key: {
                    "name": f"answer_{field.stable_key}",
                    "type": field.field_type,
                    "required": field.required,
                    "section": str(field.section_id),
                    "additional_text": additional_text_config(field),
                    "option_filter": self.option_filters.get(key),
                }
                for key, field in self.by_id.items()
            },
        }


def compare(value, operator, expected):
    match operator:
        case "IS_EMPTY":
            return empty(value)
        case "IS_NOT_EMPTY":
            return not empty(value)
        case "EQUALS":
            return value == expected
        case "NOT_EQUALS":
            return value != expected
        case "CONTAINS":
            return expected in value if isinstance(value, (str, list)) else False
        case "GREATER_THAN":
            return not empty(value) and value > expected
        case "LESS_THAN":
            return not empty(value) and value < expected
    return False
