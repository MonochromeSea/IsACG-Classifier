(function () {
  const root = document.documentElement;
  const button = document.querySelector("#themeToggle");
  if (!button) {
    return;
  }

  const savedTheme = localStorage.getItem("isacg-theme") || "light";
  root.dataset.theme = savedTheme;
  button.textContent = savedTheme === "dark" ? "浅色" : "深色";

  button.addEventListener("click", () => {
    const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = nextTheme;
    localStorage.setItem("isacg-theme", nextTheme);
    button.textContent = nextTheme === "dark" ? "浅色" : "深色";
  });
})();
