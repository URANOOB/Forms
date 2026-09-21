def welcome_data(version):
    config = version.welcome
    return {
        "title": config.get("title") or version.title or version.form.name,
        "text": config.get("text") or version.description,
        "button_label": config.get("button_label") or "Comenzar",
        "horizontal": config.get("horizontal", "right"),
        "vertical": config.get("vertical", "center"),
        "image_url": version.welcome_image.get_absolute_url() if version.welcome_image_id else "",
    }
