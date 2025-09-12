"""
Universal view shim.

This module lazily exposes view submodules by short names, so code can continue doing:
    from dashboard.views import user_views, data_collection_views, ...

It also proxies direct attributes (e.g. classes) like:
    from dashboard.views import UsernameEntryView

without requiring callers to know the new subfolder structure.
"""
from importlib import import_module

# Discovered module map (auto-generated)
_ALIAS = {
    "user_views": "dashboard.views.users.user_views",
    "it_conversations_views": "dashboard.views.messages.it_conversations_views",
    "home_views": "dashboard.views.marketing.home_views",
    "rr_budget_views": "dashboard.views.funds.rr_budget_views",
    "util_views": "dashboard.views.util_views",
    "fund_views": "dashboard.views.funds.fund_views",
    "form_views": "dashboard.views.funds.form_views",
    "submission_views": "dashboard.views.funds.submission_views",
    "senior_key_views": "dashboard.views.funds.senior_key_views",
    "iacuc_views": "dashboard.views.compliance.iacuc_views",
    "sf424_views": "dashboard.views.funds.sf424_views",
    "admin_views": "dashboard.views.admin.admin_views",
    "protocol_creation_views": "dashboard.views.compliance.protocol_creation_views",
    "org_it_admin_views": "dashboard.views.admin.org_it_admin_views",
    "active_experiment_views": "dashboard.views.experiments.active_experiment_views",
    "animal_details_views": "dashboard.views.animals.animal_details_views",
    "irb_views": "dashboard.views.compliance.irb_views",
    "conversation_views": "dashboard.views.messages.conversation_views",
    "data_collection_views": "dashboard.views.experiments.data_collection_views",
    "create_experiment_views": "dashboard.views.experiments.create_experiment_views",
    "it_admin_views": "dashboard.views.admin.it_admin_views",
    "event_views": "dashboard.views.events.event_views"
}

__all__ = sorted(list(_ALIAS.keys()))

def __getattr__(name: str):
    # If someone asks for a submodule (e.g., 'user_views'), import and return it.
    if name in _ALIAS:
        mod = import_module(_ALIAS[name])
        globals()[name] = mod
        return mod

    # Otherwise, try to find an attribute (class/function/const) exported by one of the known submodules.
    for modpath in _ALIAS.values():
        mod = import_module(modpath)
        if hasattr(mod, name):
            obj = getattr(mod, name)
            globals()[name] = obj
            return obj

    raise AttributeError(f"module 'dashboard.views' has no attribute '{name}'")

