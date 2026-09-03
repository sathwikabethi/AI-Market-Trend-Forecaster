(function () {
    try {
        const theme = localStorage.getItem('tf_theme') || 'dark'
        document.documentElement.classList.toggle('dark', theme === 'dark')
    } catch {
        document.documentElement.classList.add('dark')
    }
})()
