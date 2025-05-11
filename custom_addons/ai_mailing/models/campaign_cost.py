from odoo import models, fields, api


class MarketingCampaignCost(models.Model):
    _name = "marketing.campaign.cost"
    _description = "Marketing Campaign Cost"

    campaign_id = fields.Many2one('marketing.campaign', string="Campaign", required=True, ondelete='cascade')
    name = fields.Char(string="Description", required=True)
    cost_type = fields.Selection([
        ('creative', 'Creative Development'),
        ('media', 'Media Buying'),
        ('influencer', 'Influencer Fees'),
        ('agency', 'Agency Fees'),
        ('software', 'Software Tools'),
        ('production', 'Production Costs'),
        ('other', 'Other Expenses')
    ], string="Cost Type", required=True)
    amount = fields.Float(string="Amount", required=True)
    date = fields.Date(string="Date", default=fields.Date.today)
    notes = fields.Text(string="Notes")

    @api.model
    def create(self, vals):
        """Override create to update the parent campaign's total cost."""
        record = super(MarketingCampaignCost, self).create(vals)
        record.campaign_id._update_total_cost()
        return record

    def write(self, vals):
        """Override write to update the parent campaign's total cost."""
        result = super(MarketingCampaignCost, self).write(vals)
        if 'amount' in vals:
            for record in self:
                record.campaign_id._update_total_cost()
        return result

    def unlink(self):
        """Override unlink to update the parent campaign's total cost."""
        campaigns = self.mapped('campaign_id')
        result = super(MarketingCampaignCost, self).unlink()
        for campaign in campaigns:
            campaign._update_total_cost()
        return result
