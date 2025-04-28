from odoo import models, fields, api
import requests
import os


class HolidayEvent(models.Model):
    _name = 'holiday.event'
    _description = 'Holiday or Event'

    name = fields.Char('Name', required=True)
    date = fields.Date('Date', required=True)
    country = fields.Char('Country')
    description = fields.Text('Description')
    event_type = fields.Selection([
        ('holiday', 'Holiday'),
        ('event', 'Event')
    ], string='Type', default='holiday')

    def action_create_campaign(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Campaign',
            'res_model': 'marketing.campaign',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_name': self.name,
                'default_start_date': self.date,
                'default_context': self.description or '',
            }
        }

    @api.model
    def fetch_calendarific_events(self, country=None, year=None, api_key=None):
        print(f"calendarific events called for country {country} and year {year} with api key {api_key}")
        if not country:
            country = 'TN'
        if not api_key:
            api_key = os.getenv("CALENDARIFIC_API_KEY")
        if not year:
            year = fields.Date.today().year

        url = f"https://calendarific.com/api/v2/holidays?&api_key={api_key}&country={country}&year={year}"
        response = requests.get(url)
        print(response)
        if response.status_code == 200:
            holidays = response.json().get('response', {}).get('holidays', [])
            for h in holidays:
                self.env['holiday.event'].sudo().create({
                    'name': h['name'],
                    'date': h['date']['iso'],
                    'country': country,
                    'description': h.get('description', ''),
                    'event_type': 'holiday'
                })
        else:
            raise Exception(f"Failed to fetch holidays: {response.text}")
