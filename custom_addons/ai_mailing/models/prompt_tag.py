from odoo  import fields, models


class PromptTag(models.Model):
    _name = 'prompt.tag'
    _description = 'Prompt Tag'
    _order ='sequence,id'

    name =fields.Char(string='Name',required=True)
    sequence = fields.Integer(default=10)
