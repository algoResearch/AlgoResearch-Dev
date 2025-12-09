"""
URL patterns for AI-powered features
"""

from django.urls import path
from dashboard.views import ai_views

app_name = 'ai'

urlpatterns = [
    # AI Assistant chat interface
    path('assistant/', ai_views.ai_assistant, name='assistant'),

    # API endpoints
    path('api/summarize/', ai_views.summarize_text, name='summarize'),
    path('api/sentiment/', ai_views.analyze_sentiment, name='sentiment'),
    path('api/keywords/', ai_views.extract_keywords, name='keywords'),
    path('api/research-suggestions/', ai_views.research_suggestions, name='research_suggestions'),
]
