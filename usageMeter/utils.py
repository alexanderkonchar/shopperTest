import base64
import json

from django.http import HttpResponse


def get_json(request_body):
    return json.loads(request_body.decode('utf-8'))


def decode_image(image):
    return base64.b64decode(image)


def return_status_400(res):
    return HttpResponse(json.dumps(res), status=400)
