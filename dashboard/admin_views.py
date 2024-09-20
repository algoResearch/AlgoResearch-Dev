from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from .forms import CustomUserCreationForm
from .models import User, Experiment
from django.db.models import Q
from .models import UserAction

@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request):
    users = User.objects.all()  # Fetch all users
    return render(request, 'admin/admin_dashboard.html', {'users': users})


# In your create_user view
def create_user(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_organization_admin = request.POST.get('is_organization_admin', False) == 'on'
            user.save()
            return redirect('admin_user_list')
    else:
        form = CustomUserCreationForm()

    return render(request, 'admin/create_user.html', {'form': form})


# View to list users (admin-only)
@user_passes_test(lambda u: u.is_superuser)
def user_list(request):
    users = User.objects.all()
    return render(request, 'admin/user_list.html', {'users': users})



def user_list(request):
    users = User.objects.all()  # Fetch all users from the database
    return render(request, 'admin/user_list.html', {'users': users})



def user_experiments(request, user_id):
    user = get_object_or_404(User, id=user_id)
    experiments = Experiment.objects.filter(
        Q(owner=user) | Q(collaborators__user=user)
    ).distinct()

    context = {
        'user': user,
        'experiments': experiments
    }
    return render(request, 'admin/user_experiments.html', context)

def view_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    return render(request, 'admin/view_user.html', {'user': user})

@login_required
def user_actions(request, user_id):
    user = get_object_or_404(User, id=user_id)
    actions = UserAction.objects.filter(user=user).order_by('-timestamp')

    return render(request, 'admin/user_actions.html', {
        'user': user,
        'actions': actions,
    })