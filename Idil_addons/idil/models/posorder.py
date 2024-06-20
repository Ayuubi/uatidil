from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_round
import logging
import time

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_pos_order_paid(self):
        _logger.info("Starting action_pos_order_paid for order: %s", self.name)
        super(PosOrder, self).action_pos_order_paid()

        if self.state == 'paid':
            self.create_transaction_booking()
            self.create_transaction_booking_lines()
        return True

    def create_transaction_booking(self):
        for order in self:
            payment_method = self.determine_payment_method(order)
            balance = order.amount_total - order.amount_paid
            try:
                transaction_booking = self.env['idil.transaction_booking'].with_context(skip_validations=True).create({
                    'transaction_number': order.id,
                    'order_number': order.name,
                    'trx_source_id': 10,
                    'payment_method': payment_method,
                    'payment_status': 'paid' if order.amount_total == order.amount_paid else 'partial_paid',
                    'trx_date': order.date_order,
                    'amount': order.amount_total,
                    'amount_paid': order.amount_paid,
                    'remaining_amount': balance
                })
                self.env.cr.commit()  # Commit the transaction
                _logger.info("Transaction Booking ID: %s", transaction_booking.id)
            except Exception as e:
                _logger.error("Error creating transaction booking for order %s: %s", order.name, str(e))
                raise ValidationError(_("Error creating transaction booking: %s") % str(e))

    def create_transaction_booking_lines(self):
        for order in self:
            try:
                time.sleep(1)  # Add a brief delay to allow the transaction to be committed
                transaction_booking = self.env['idil.transaction_booking'].search(
                    [('order_number', '=', order.name)], limit=1)
                if not transaction_booking:
                    _logger.error("Transaction booking not found for order %s", order.name)
                    raise ValidationError(_("Transaction booking not found for order %s") % order.name)

                for line in order.lines:
                    # Create debit line
                    debit_line_vals = {
                        'transaction_booking_id': transaction_booking.id,
                        'description': line.product_id.name,
                        # 'product_id': line.product_id.id,
                        'account_number': 1,  # Adjust as necessary
                        'transaction_type': 'dr',
                        'dr_amount': round(line.price_subtotal, 2),  # Adjust amount as necessary
                        'cr_amount': 0.0,
                        'transaction_date': order.date_order
                    }
                    self.env['idil.transaction_bookingline'].create(debit_line_vals)
                    _logger.info("Created debit booking line for product: %s", line.product_id.name)

                    # Create credit line
                    credit_line_vals = {
                        'transaction_booking_id': transaction_booking.id,
                        'description': line.product_id.name,
                        # 'product_id': line.product_id.id,
                        'account_number': 2,  # Adjust as necessary
                        'transaction_type': 'cr',
                        'dr_amount': 0.0,
                        'cr_amount': round(line.price_subtotal, 2),  # Adjust amount as necessary
                        'transaction_date': order.date_order
                    }
                    self.env['idil.transaction_bookingline'].create(credit_line_vals)
                    _logger.info("Created credit booking line for product: %s", line.product_id.name)

            except Exception as e:
                _logger.error("Error creating transaction booking lines for order %s: %s", order.name, str(e))
                raise ValidationError(_("Error creating transaction booking lines: %s") % str(e))

    def determine_payment_method(self, order):
        for payment in order.payment_ids:
            if payment.payment_method_id.is_cash_count:
                return 'cash'
            elif 'bank' in payment.payment_method_id.name.lower():
                return 'bank_transfer'
        return 'other'
