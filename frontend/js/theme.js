function applyTheme(theme){
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("nv_theme", theme);
  document.querySelectorAll("[data-theme-toggle]").forEach(btn=>{
    btn.setAttribute("aria-pressed", theme === "dark");
    const sun = btn.querySelector(".icon-sun");
    const moon = btn.querySelector(".icon-moon");
    if(sun && moon){
      sun.style.display = theme === "dark" ? "block" : "none";
      moon.style.display = theme === "dark" ? "none" : "block";
    }
  });
}

function initTheme(){
  const saved = localStorage.getItem("nv_theme")
    || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(saved);
  document.querySelectorAll("[data-theme-toggle]").forEach(btn=>{
    btn.addEventListener("click", ()=>{
      const current = document.documentElement.getAttribute("data-theme");
      applyTheme(current === "dark" ? "light" : "dark");
    });
  });
}

document.addEventListener("DOMContentLoaded", initTheme);
