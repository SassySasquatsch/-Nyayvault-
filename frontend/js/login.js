document.addEventListener("DOMContentLoaded", ()=>{
  const form = document.getElementById("loginForm");
  const errorBox = document.getElementById("formError");
  const togglePw = document.getElementById("togglePw");
  const pwInput = document.getElementById("password");

  togglePw.addEventListener("click", ()=>{ pwInput.type = pwInput.type === "password" ? "text" : "password"; });

  form.addEventListener("submit", async (e)=>{
    e.preventDefault();
    const username = document.getElementById("username").value.trim();
    const password = pwInput.value;
    const role = document.getElementById("role").value;
    const submit = form.querySelector('button[type="submit"]');
    if(!username || !password){ errorBox.textContent="Enter username and password."; errorBox.classList.add("visible"); return; }
    errorBox.classList.remove("visible");
    submit.disabled = true;
    try{
      const result = await NV_API.login(username,password,role);
      localStorage.setItem("nv_token", result.access_token);
      localStorage.setItem("nv_role", result.user.role);
      localStorage.setItem("nv_user", result.user.username);
      localStorage.setItem("nv_full_name", result.user.full_name);
      window.location.href = "/dashboard.html";
    }catch(err){
      errorBox.textContent = err.message;
      errorBox.classList.add("visible");
    }finally{ submit.disabled=false; }
  });
});
