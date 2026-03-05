document.addEventListener('DOMContentLoaded', () => {
    
    // --- Mobile Sidebar Logic ---
    const mobileToggle = document.getElementById('mobile-toggle');
    const sidebar = document.getElementById('sidebar');
    
    if(mobileToggle){
        mobileToggle.addEventListener('click', (e) => {
            e.stopPropagation(); // Stop click from closing it immediately
            sidebar.classList.toggle('active');
        });
    }

    // --- Chat Widget Logic ---
    const chatBtn = document.getElementById('chatToggleBtn');
    const chatWindow = document.getElementById('chatWindow');
    const closeChat = document.getElementById('closeChatBtn');

    if(chatBtn) {
        // 1. Open Chat
        chatBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // Stop bubbling
            chatWindow.classList.toggle('active');
        });

        // 2. Close with X button
        closeChat.addEventListener('click', () => {
            chatWindow.classList.remove('active');
        });

        // 3. Global Click Listener (Handles clicking outside)
        document.addEventListener('click', (e) => {
            // Mobile Sidebar Close Logic
            if (window.innerWidth <= 768 && sidebar.classList.contains('active')) {
                if (!sidebar.contains(e.target) && !mobileToggle.contains(e.target)) {
                    sidebar.classList.remove('active');
                }
            }

            // Chat Close Logic
            if (chatWindow.classList.contains('active')) {
                // If click is NOT inside chat window AND NOT on the toggle button
                if (!chatWindow.contains(e.target) && !chatBtn.contains(e.target)) {
                    chatWindow.classList.remove('active');
                }
            }
        });
    }
});