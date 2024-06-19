   odoo.define('your_module_name.pos_custom_product', function (require) {
    "use strict";

    const models = require('point_of_sale.models');
    const PosModelSuper = models.PosModel.prototype;

    models.load_models([{
        model: 'my_product.product',
        fields: [
            'id', 'name', 'sale_price', 'taxes_id', 'barcode',
            'internal_reference', 'type', 'uom_id', 'sales_description',
            'category_id', 'stock_quantity'
        ],
        domain: function (self) { return [['available_in_pos', '=', true]]; },
        loaded: function (self, products) {
            self.db.add_products(products);
        },
    }], {
        after: 'product.product'
    });

});
