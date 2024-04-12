from odoo import models, fields, api


class ModelA(models.Model):
    _name = 'model.a'
    _description = 'Model A'

    # Other fields definition

    @api.model
    def delete_other_models_data(self, *args, **kwargs):
        # Add the logic to delete records from ModelB, ModelC, etc.
        self.env['idil.purchase_order.line'].search([]).unlink()
        self.env['idil.purchase_order'].search([]).unlink()

        self.env['idil.salesperson.place.order.line'].search([]).unlink()
        self.env['idil.salesperson.place.order'].search([]).unlink()

        self.env['idil.sale.order.line'].search([]).unlink()
        self.env['idil.sale.order'].search([]).unlink()

        self.env['idil.transaction_bookingline'].search([]).unlink()
        self.env['idil.transaction_booking'].search([]).unlink()

        self.env['idil.manufacturing.order.line'].search([]).unlink()
        self.env['idil.manufacturing.order'].search([]).unlink()
