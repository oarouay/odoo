from odoo import models, fields, api


class UtmCampaign(models.Model):
    """Extend UTM Campaign to add reference to marketing campaigns."""
    _inherit = 'utm.campaign'

    marketing_campaign_id = fields.Many2one(
        'marketing.campaign',
        string='Marketing Campaign',
        ondelete='set null',  # If marketing campaign is deleted, keep the UTM campaign
        help="The marketing campaign associated with this UTM campaign"
    )