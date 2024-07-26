/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";

patch(WebClient.prototype, "idil.WebClient", {
    setup() {
        this._super.apply(this, arguments);
        this.title.setParts({ zopenerp: "My Custom Title" });
    },
});
