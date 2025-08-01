// Toggle a dropdown open/close
function toggleDropdown(button) {
    const currentMenu = button.nextElementSibling;
    const allMenus = document.querySelectorAll('.dropdown-content');
    const allButtons = document.querySelectorAll('.dropbtn');

    // Close all other dropdowns
    allMenus.forEach(menu => {
        if (menu !== currentMenu) {
            menu.classList.remove('show');
        }
    });

    allButtons.forEach(btn => btn.classList.remove('active-drop'));

    const isOpen = currentMenu.classList.contains('show');
    currentMenu.classList.toggle('show', !isOpen);

    if (!isOpen) {
        button.classList.add('active-drop');
    }
}

// Close dropdown via the X button
function closeDropdown(button) {
    const dropdown = button.parentElement;
    dropdown.classList.remove('show');

    document.querySelectorAll('.dropbtn').forEach(btn => {
        btn.classList.remove('active-drop');
    });
}

// Toggle the mobile menu (hamburger)
function toggleMobileMenu() {
    const navContent = document.querySelector('.navbar-content');
    navContent.classList.toggle('active');
}

// Close dropdowns when clicking outside
document.addEventListener('click', function (e) {
    const isDropdownClick = e.target.closest('.dropdown');
    if (!isDropdownClick) {
        document.querySelectorAll('.dropdown-content').forEach(menu => {
            menu.classList.remove('show');
        });
        document.querySelectorAll('.dropbtn').forEach(btn => {
            btn.classList.remove('active-drop');
        });
    }
});
