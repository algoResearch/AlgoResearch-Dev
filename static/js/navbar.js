function toggleDropdown(button) {
    document.querySelectorAll('.dropdown-content').forEach(menu => {
        if (menu !== button.nextElementSibling) {
            menu.style.display = 'none';
        }
    });

    const menu = button.nextElementSibling;
    const isOpen = menu.style.display === 'block';

    document.querySelectorAll('.dropbtn').forEach(btn => {
        btn.classList.remove('active-drop');
    });

    if (isOpen) {
        menu.style.display = 'none';
    } else {
        menu.style.display = 'block';
        button.classList.add('active-drop');
    }
}

document.addEventListener('click', function (e) {
    const isDropdown = e.target.matches('.dropbtn') || e.target.closest('.dropdown');
    if (!isDropdown) {
        document.querySelectorAll('.dropdown-content').forEach(menu => menu.style.display = 'none');
        document.querySelectorAll('.dropbtn').forEach(btn => btn.classList.remove('active-drop'));
    }
});
