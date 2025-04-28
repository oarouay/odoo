from odoo import models, fields, api
from odoo.http import request


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tracker_click_id = fields.Many2one('link.tracker.click', string='Tracker Click')
    @api.model
    def create(self, vals):
        order = super().create(vals)
        click_id = request.httprequest.cookies.get('odoo_click_id')
        if click_id:
            click = self.env['link.tracker.click'].browse(int(click_id))
            if click.exists():
                click.sale_id = order.id
        return order