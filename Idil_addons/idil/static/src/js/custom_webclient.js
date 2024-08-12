
class CustomWebClient extends WebClient {
    setup() {
        super.setup();
        this.title.setParts({ zopenerp: "Idil" });
    }
}

registry.category("main_components").add("WebClient", CustomWebClient);
