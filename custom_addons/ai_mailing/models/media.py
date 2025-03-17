from odoo import models, fields, api

class ImageModel(models.Model):
    _name = 'image.model'
    _description = 'Model for storing an image with its name and description'

    name = fields.Char(string='Image Name', required=True)
    description = fields.Text(string='Description')
    url = fields.Char(string='URL')
    urldes = fields.Char(string="AI Prompt", compute='_compute_ai_prompt', store=True)

    @api.depends('url', 'description')
    def _compute_ai_prompt(self):
        for record in self:
            # Concatenate the image URL and description, separated by a comma
            record.urldes = f"the image url :{record.url}, the description of image :{record.description}." if record.url and record.description else ''