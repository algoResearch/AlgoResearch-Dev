"""
AI-powered views using Google Gemini
"""

from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from dashboard.services.gemini_service import get_gemini_service


@login_required
@require_http_methods(["GET", "POST"])
def ai_assistant(request):
    """
    Main AI assistant view - provides a chat interface with Gemini.
    """
    if request.method == "GET":
        return render(request, 'dashboard/ai_assistant.html')

    try:
        data = json.loads(request.body)
        prompt = data.get('prompt', '')

        if not prompt:
            return JsonResponse({'error': 'No prompt provided'}, status=400)

        gemini = get_gemini_service()

        if not gemini.is_configured():
            return JsonResponse({
                'error': 'AI service not configured. Please contact administrator.'
            }, status=503)

        response = gemini.generate_text(prompt)

        if response:
            return JsonResponse({'response': response})
        else:
            return JsonResponse({
                'error': 'Failed to generate response'
            }, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def summarize_text(request):
    """
    API endpoint to summarize text using Gemini.

    Expected POST data:
    {
        "text": "Long text to summarize...",
        "max_length": 500  // optional, defaults to 500 words
    }
    """
    try:
        data = json.loads(request.body)
        text = data.get('text', '')
        max_length = data.get('max_length', 500)

        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        gemini = get_gemini_service()

        if not gemini.is_configured():
            return JsonResponse({
                'error': 'AI service not configured'
            }, status=503)

        summary = gemini.summarize_text(text, max_length)

        if summary:
            return JsonResponse({
                'summary': summary,
                'original_length': len(text.split()),
                'summary_length': len(summary.split())
            })
        else:
            return JsonResponse({
                'error': 'Failed to generate summary'
            }, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def analyze_sentiment(request):
    """
    API endpoint to analyze sentiment of text.

    Expected POST data:
    {
        "text": "Text to analyze..."
    }
    """
    try:
        data = json.loads(request.body)
        text = data.get('text', '')

        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        gemini = get_gemini_service()

        if not gemini.is_configured():
            return JsonResponse({
                'error': 'AI service not configured'
            }, status=503)

        analysis = gemini.analyze_sentiment(text)

        if analysis:
            return JsonResponse(analysis)
        else:
            return JsonResponse({
                'error': 'Failed to analyze sentiment'
            }, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def extract_keywords(request):
    """
    API endpoint to extract keywords from text.

    Expected POST data:
    {
        "text": "Text to extract keywords from...",
        "max_keywords": 10  // optional
    }
    """
    try:
        data = json.loads(request.body)
        text = data.get('text', '')
        max_keywords = data.get('max_keywords', 10)

        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        gemini = get_gemini_service()

        if not gemini.is_configured():
            return JsonResponse({
                'error': 'AI service not configured'
            }, status=503)

        keywords = gemini.extract_keywords(text, max_keywords)

        if keywords:
            return JsonResponse({'keywords': keywords})
        else:
            return JsonResponse({
                'error': 'Failed to extract keywords'
            }, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def research_suggestions(request):
    """
    API endpoint to generate research suggestions.

    Expected POST data:
    {
        "research_area": "Machine Learning",
        "current_focus": "Neural Networks"  // optional
    }
    """
    try:
        data = json.loads(request.body)
        research_area = data.get('research_area', '')
        current_focus = data.get('current_focus')

        if not research_area:
            return JsonResponse({'error': 'No research area provided'}, status=400)

        gemini = get_gemini_service()

        if not gemini.is_configured():
            return JsonResponse({
                'error': 'AI service not configured'
            }, status=503)

        suggestions = gemini.generate_research_suggestions(
            research_area,
            current_focus
        )

        if suggestions:
            return JsonResponse({'suggestions': suggestions})
        else:
            return JsonResponse({
                'error': 'Failed to generate suggestions'
            }, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
