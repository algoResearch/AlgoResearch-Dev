from django.urls import path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

from dashboard import user_views, active_experiment_views, animal_details_views, conversation_views, data_collection_views, create_experiment_views, event_views

urlpatterns = [
    # Home and Authentication URLs
    path('', user_views.home, name='home'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('register/', user_views.register, name='register'),

    # Dashboard
    path('dashboard/', user_views.dashboard, name='dashboard'),

    # Experiment-related URLs
    path('all-experiments/', active_experiment_views.all_experiments, name='all_experiments'),
    path('experiments/<int:experiment_id>/save-rfids/', data_collection_views.save_rfids, name='save_rfids'),  # Correct reference here
    path('create-experiment/', create_experiment_views.create_experiment, name='create_experiment'),
    path('experiment-summary/<int:experiment_id>/', active_experiment_views.experiment_summary, name='experiment_summary'),
    path('experiment-home/<int:experiment_id>/', active_experiment_views.experiment_home, name='experiment_home'),
    path('map-rfid/<int:experiment_id>/', active_experiment_views.map_rfid, name='map_rfid'),
    path('cage-configuration/<int:experiment_id>/', active_experiment_views.cage_configuration, name='cage_configuration'),
    path('cage-configuration/<int:experiment_id>/update/', active_experiment_views.update_cage_configuration, name='update_cage_configuration'),
    path('update-cages/<int:experiment_id>/', active_experiment_views.update_cages, name='update_cages'),
    path('analytics/<int:experiment_id>/', data_collection_views.analytics, name='analytics'),
    path('delete-experiment/<int:experiment_id>/', active_experiment_views.delete_experiment, name='delete_experiment'),
    path('view-experiment/<int:experiment_id>/', active_experiment_views.view_experiment, name='view_experiment'),
    path('experiment/<int:experiment_id>/animals/', animal_details_views.animals, name='animals'),
    path('animal-details/<int:experiment_id>/<int:animal_index>/', animal_details_views.animal_details, name='animal_details'),
    path('animal/<int:experiment_id>/<int:animal_index>/delete/', animal_details_views.delete_animal, name='delete_animal'),
    path('add-comment/<int:experiment_id>/<int:animal_index>/', animal_details_views.add_comment, name='add_comment'),
    path('download-csv/<int:experiment_id>/', data_collection_views.download_csv, name='download_csv'),
    path('strain-analytics/<str:strain_name>/', data_collection_views.strain_analytics, name='strain_analytics'),
    path('experiment/<int:experiment_id>/settings/', active_experiment_views.experiment_settings, name='experiment_settings'),
    path('end-experiment/<int:experiment_id>/', active_experiment_views.end_experiment, name='end_experiment'),
    path('delete-multiple-experiments/', active_experiment_views.delete_multiple_experiments, name='delete_multiple_experiments'),
    path('add-collaborator/', user_views.add_collaborator, name='add_collaborator'),
    path('update-collaborator-role/', user_views.update_collaborator_role, name='update_collaborator_role'),
    path('respond-invitation/', user_views.respond_invitation, name='respond_invitation'),
    path('remove-animal/<int:experiment_id>/<int:animal_index>/', animal_details_views.remove_animal, name='remove_animal'),
    path('remove-collaborator/', user_views.remove_collaborator, name='remove_collaborator'),
    path('update-collaborator-role/', user_views.update_collaborator_role, name='update_collaborator_role'),
    path('animal/<int:experiment_id>/<int:animal_index>/update/', animal_details_views.update_overview, name='update_overview'),
    path('experiment/<int:experiment_id>/animal/<int:animal_index>/add-observation/', animal_details_views.add_observation, name='add_observation'),
    path('animal/<int:animal_id>/save-observations/', animal_details_views.save_observations, name='save_observations'),
    path('experiment/<int:experiment_id>/animal/<int:animal_index>/add-sample/', animal_details_views.add_sample, name='add_sample'),
    path('experiment/<int:experiment_id>/animal/<int:animal_index>/add-dose/', animal_details_views.add_dose, name='add_dose'),
    path('experiments/<int:experiment_id>/update/', active_experiment_views.update_experiment, name='update_experiment'),
    path('experiments/<int:experiment_id>/get-assignments/', active_experiment_views.get_rfid_assignments, name='get_rfid_assignments'),
    path('data-collection/<int:experiment_id>/save/', data_collection_views.save_data_collection, name='save_data_collection'),
    path('experiment/<int:experiment_id>/data-collection/reset-session/', data_collection_views.reset_weigh_in_session, name='reset_weigh_in_session'),
    path('experiment/<int:experiment_id>/data-collection/', data_collection_views.data_collection, name='data_collection'),
    path('experiment/<int:experiment_id>/data-collection/simulate-scan/', data_collection_views.simulate_scan, name='simulate_scan'),
    path('experiment/<int:experiment_id>/data-collection/enter-weight/', data_collection_views.enter_weight, name='enter_weight'),
    path('experiment/<int:experiment_id>/data-collection/enter-tumor-size/', data_collection_views.enter_tumor_size, name='enter_tumor_size'),
    path('experiment/<int:experiment_id>/data-collection/start-session/', data_collection_views.start_weighing_session, name='start_weighing_session'),
    path('experiment/<int:experiment_id>/data-collection/end-session/', data_collection_views.end_weigh_in_session, name='end_weigh_in_session'),
    path('events/', event_views.events, name='events'),
    path('add-event/', event_views.add_event, name='add_event'),
    path('delete-calendar-event/<int:event_id>/', event_views.delete_calendar_event, name='delete_calendar_event'),
    path('userhome/', user_views.user_home, name='user_home'),
    path('profile/', user_views.profile, name='profile'),
    path('update-profile-picture/', user_views.update_profile_picture, name='update_profile_picture'),
    path('add-friend/', user_views.add_friend, name='add_friend'),
    path('remove-friend/', user_views.remove_friend, name='remove_friend'),
    path('pending-requests/', user_views.pending_requests, name='pending_requests'),
    path('respond-friend-request/', user_views.respond_friend_request, name='respond_friend_request'),
    path('friend-info/<int:friend_id>/', user_views.friend_info, name='friend_info'),
    path('messages/', conversation_views.messages, name='messages'),
    path('conversation/<int:conversation_id>/', conversation_views.conversation, name='conversation'),
    path('conversations/', conversation_views.conversations, name='conversations'),
    path('new_message/', conversation_views.new_message, name='new_message'),
    path('send-new-message/', conversation_views.send_new_message, name='send_new_message'),
    path('send-message/<int:conversation_id>/', conversation_views.send_message, name='send_message'),
    path('ajax/conversation/<int:conversation_id>/', conversation_views.ajax_conversation_details, name='ajax_conversation_details'),
    path('delete-conversation/<int:conversation_id>/', conversation_views.delete_conversation, name='delete_conversation'),
    path('create-group/', user_views.create_group, name='create_group'),
    path('experiments/<int:experiment_id>/get-rfids/', active_experiment_views.get_rfid_assignments, name='get_rfid_assignments'),
    path('Studies/', data_collection_views.Studies, name='Studies'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Serve media and static files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
