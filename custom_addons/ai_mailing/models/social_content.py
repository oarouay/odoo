from odoo import models, fields

class GeneratedContent(models.Model):
    _name = "generated.content"
    _description = "Generated Content"

    campaign_id = fields.Many2one('marketing.campaign', string="Campaign", ondelete='cascade')
    platform = fields.Selection([
        ('email', 'Email'),
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('whatsapp', 'WhatsApp')
    ], string="Platform", required=True)
    content = fields.Text(string="Content", required=True)
    generated_on = fields.Datetime(string="Generated On", default=lambda self: fields.Datetime.now())