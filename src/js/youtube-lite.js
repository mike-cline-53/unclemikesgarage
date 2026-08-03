(function () {
  function loadPlayer(container) {
    var id = container.getAttribute("data-id");
    if (!id) return;

    var iframe = document.createElement("iframe");
    iframe.src =
      "https://www.youtube-nocookie.com/embed/" +
      encodeURIComponent(id) +
      "?autoplay=1&rel=0";
    iframe.title = "YouTube video";
    iframe.allow =
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    iframe.allowFullscreen = true;
    iframe.loading = "eager";

    container.textContent = "";
    container.appendChild(iframe);
  }

  function onActivate(event) {
    var btn = event.target.closest(".youtube-lite__btn");
    if (!btn) return;
    var container = btn.closest(".youtube-lite");
    if (container) loadPlayer(container);
  }

  document.addEventListener("click", onActivate);
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var btn = event.target.closest(".youtube-lite__btn");
    if (!btn) return;
    event.preventDefault();
    var container = btn.closest(".youtube-lite");
    if (container) loadPlayer(container);
  });
})();
