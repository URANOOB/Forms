from django.shortcuts import render


def home(request):
    return render(request, "home.html")


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)
