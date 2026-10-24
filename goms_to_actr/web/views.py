"""Stateless HTTP adapter around the same parser and compiler as the CLI."""
import json

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from goms_to_actr import ModelError, compile_model, loads
from .examples import EXAMPLES


@require_GET
def index(request):
    return render(request, 'converter/index.html', {'examples': EXAMPLES})


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key {key!r}')
        result[key] = value
    return result


# This public endpoint accepts only JSON, uses no authentication/cookies, and
# changes no server state. Exemption lets non-browser clients call it directly.
@csrf_exempt
@never_cache
def convert(request):
    if request.method != 'POST':
        response = JsonResponse({'error': 'Use POST with a JSON body.'}, status=405)
        response['Allow'] = 'POST'
        return response
    if request.content_type != 'application/json':
        return JsonResponse({'error': 'Content-Type must be application/json.'}, status=415)
    try:
        body = request.body
        if len(body) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
            raise RequestDataTooBig
        payload = json.loads(body.decode('utf-8'), object_pairs_hook=unique_fields)
    except RequestDataTooBig:
        return JsonResponse({'error': 'Request body exceeds the 256 KiB limit.'}, status=413)
    except (ValueError, RecursionError):
        return JsonResponse({'error': 'Request body must be valid UTF-8 JSON with unique keys.'}, status=400)
    if not isinstance(payload, dict) or set(payload) != {'format', 'source'}:
        return JsonResponse({'error': 'Provide exactly two fields: format and source.'}, status=400)
    source_format = payload['format']
    if source_format not in ('json', 'ngomsl'):
        return JsonResponse({'error': 'format must be json or ngomsl.'}, status=400)
    source = payload['source']
    if not isinstance(source, str) or not source.strip():
        return JsonResponse({'error': 'source must be a nonempty string.'}, status=400)
    try:
        model = loads(source, format=source_format)
        lisp = compile_model(model, max_states=settings.CONVERSION_MAX_STATES,
                             max_output_bytes=settings.CONVERSION_MAX_OUTPUT_BYTES)
    except (ModelError, ValueError, RecursionError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse({'name': model['name'], 'format': source_format, 'lisp': lisp})
