class DashPanel extends HTMLElement {
  set hass(hass) {
    if (!this._iframe) {
      this._iframe = document.createElement("iframe");
      this._iframe.style.cssText = "width:100%;height:100%;border:0;display:block;";
      this._iframe.src = "/dash/frontend/dash-app.html";
      this._ready = false;
      this._pendingToken = null;

      this._iframe.addEventListener("load", () => {
        this._ready = true;
        if (this._pendingToken) {
          this._post(this._pendingToken);
          this._pendingToken = null;
        }
      });

      this.appendChild(this._iframe);
    }

    const token = hass.auth.data.access_token;
    if (this._ready) {
      this._post(token);
    } else {
      this._pendingToken = token;
    }
  }

  _post(token) {
    this._iframe.contentWindow.postMessage(
      { type: "auth", token },
      window.location.origin
    );
  }

  connectedCallback() {
    this.style.cssText = "display:block;height:100vh;overflow:hidden;";
  }
}

customElements.define("dash-panel", DashPanel);
