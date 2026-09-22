from django import forms


class OptionImageMixin:
    def __init__(self, image_urls, *args, **kwargs):
        self.image_urls = image_urls
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, **kwargs):
        option = super().create_option(name, value, label, selected, index, **kwargs)
        option["image_url"] = self.image_urls.get(str(value), "")
        if option["image_url"]:
            option["attrs"]["data-choice-image"] = option["image_url"]
        return option


class ImageSelect(OptionImageMixin, forms.Select):
    pass


class ImageRadioSelect(OptionImageMixin, forms.RadioSelect):
    option_template_name = "forms/widgets/image_choice.html"


class ImageCheckboxSelectMultiple(OptionImageMixin, forms.CheckboxSelectMultiple):
    option_template_name = "forms/widgets/image_choice.html"
