odoo.define('Idil.PosCustomProducts', function (require) {
    'use strict';

    console.log("Custom POS Products JavaScript Loaded");  // Ensure this logs

    var models = require('point_of_sale.models');

    models.load_fields('product.product', ['name', 'list_price', 'qty_available', 'image_1920']);

    models.load_models([{
        model: 'my_product.product',
        fields: ['name', 'sale_price', 'stock_quantity', 'image_1920', 'available_in_pos'],
        domain: function(self) {
            return [['available_in_pos', '=', true]];
        },
        loaded: function(self, products) {
            console.log("Loaded custom products: ", products);  // Ensure this logs
            var product_db = self.db.add_products(_.map(products, function(product) {
                return {
                    id: product.id,
                    display_name: product.name,
                    list_price: product.sale_price,
                    qty_available: product.stock_quantity,
                    image_url: '/web/image?model=my_product.product&id=' + product.id + '&field=image_1920',
                };
            }));
            console.log("Custom Products added to POS DB: ", product_db);  // Ensure this logs
        },
    }], {'after': 'product.product'});
});
