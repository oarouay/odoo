import google.generativeai as genai
from odoo.exceptions import UserError
from odoo import models, fields, api, _
from datetime import datetime, date
import json
from math import floor


class MarketingCampaign(models.Model):
    _name = "marketing.campaign"
    _description = "Marketing Campaign"
    _inherit = ["mail.thread"]

    company_id = fields.Many2one('res.company', string='Company', index=True, default=lambda self: self.env.company)
    # Campaign Basic Information
    name = fields.Char(string="Campaign Name", required=True)
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")
    user_id = fields.Many2one('res.users', string='Responsible User', default=lambda self: self.env.user, tracking=True)
    record_color = fields.Integer('Color Index', compute='_compute_record_color')

    color = fields.Integer(string='Color Index', default=0)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled')
    ], string="Status", default='draft', group_expand="_read_group_stage_ids", tracking=True)

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        return [key for key, _ in self._fields['status'].selection]

    content_strategy = fields.Selection([
        ('engagement', 'Engagement'),
        ('sales', 'Sales'),
        ('awareness', 'Brand Awareness')
    ], string="Content Strategy")
    post_frequency = fields.Char(string="Post Frequency", compute="_compute_post_frequency", store=True)
    context = fields.Text(string="Context")
    tag_ids = fields.Many2many('prompt.tag', string='Tags')
    image_ids = fields.Many2many('image.model', string='Images')
    link_ids = fields.Many2many('link.model', string='Links')

    # Tracking fields
    tracked_link_ids = fields.One2many('link.tracker', 'campaign_id1', string="Tracked Links")

    email_ids = fields.One2many('social.email', 'campaign_id', string="Emails")
    x_ids = fields.One2many('social.x', 'campaign_id', string="Tweets")
    instagram_ids = fields.One2many('social.instagram', 'campaign_id', string="Instagram Posts")
    facebook_ids = fields.One2many('social.facebook', 'campaign_id', string="Facebook Posts")

    # AI-Generated Email Content
    product_tags = fields.Many2many(
        'product.product',
        relation='marketing_campaign_product_rel',
        column1='campaign_id',
        column2='product_id',
        string="Tagged Products",
        domain=lambda self: [('is_published', '=', True)]
    )

    # Dashboard statistics
    click_count = fields.Integer(compute='_compute_campaign_stats', string="Total Clicks")
    unique_click_count = fields.Integer(compute='_compute_campaign_stats', string="Unique Clicks")
    conversion_rate = fields.Float(compute='_compute_campaign_stats', string="Conversion Rate (%)")
    total_sales = fields.Integer(compute='_compute_campaign_stats', string="Total Sales")
    total_revenue = fields.Float(compute='_compute_campaign_stats', string="Total Revenue")
    product_links = fields.Text(string="Product Links", compute="_compute_product_links", store=True)

    cost = fields.Float(string="Total Cost", compute="_update_total_cost", store=True)
    cost_details_ids = fields.One2many('marketing.campaign.cost', 'campaign_id', string="Cost Details")

    show_canceled_alert = fields.Boolean(compute='_compute_show_alerts', store=False)
    show_completed_alert = fields.Boolean(compute='_compute_show_alerts', store=False)

    apply_discount = fields.Boolean(string="Apply Discount", default=False, tracking=True)
    discount_type = fields.Selection([
        ('percent', 'Percentage'),
        ('fixed', 'Fixed Amount')
    ], string="Discount Type", default='percent', tracking=True)
    discount_value = fields.Float(string="Discount Value", tracking=True)


    def action_apply_campaign_discount(self):
        """
        Apply the campaign discount to all linked products and make it effective.
        """
        self.ensure_one()
        # 1) Pre‑checks
        if not self.apply_discount:
            raise UserError(_("Please tick 'Apply Discount' on the campaign first."))
        if not self.product_tags:
            raise UserError(_("No products tagged—add at least one product to apply discounts."))
        if not self.discount_value:
            raise UserError(_("Please set a discount value greater than zero."))

        # 2) Locate or create a campaign‑specific pricelist
        pricelist_name = f"Campaign {self.name} Discount"
        pricelist = self.env['product.pricelist'].search([
            ('name', '=', pricelist_name),
        ], limit=1)

        if not pricelist:
            pricelist = self.env['product.pricelist'].create({
                'name': pricelist_name,
                'currency_id': self.env.company.currency_id.id,
                'active': True,
                'sequence': 1,  # Lower sequence = higher priority
            })

        # 3) Create or update pricelist items for each product
        for product in self.product_tags:
            # Check for existing item
            print(product.id,product.product_tmpl_id)
            existing_item = self.env['product.pricelist.item'].search([
                ('pricelist_id', '=', pricelist.id),
                ('product_id', '=', product.id),
                ('applied_on', '=', '0_product_variant'),
            ], limit=1)

            # Prepare values based on discount type
            if self.discount_type == 'percent':
                vals = {
                    'pricelist_id': pricelist.id,
                    'product_id': product.id,
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'applied_on': '0_product_variant',
                    'compute_price': 'percentage',
                    'percent_price': self.discount_value,  # Positive value for discount percentage
                    'min_quantity': 1,
                    'date_start': self.start_date,
                    'date_end': self.end_date,
                }
            else:  # fixed amount
                vals = {
                    'pricelist_id': pricelist.id,
                    'product_id': product.id,
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'applied_on': '0_product_variant',
                    'compute_price': 'fixed',
                    'fixed_price': max(0, product.lst_price - self.discount_value),
                    'min_quantity': 1,
                    'date_start': self.start_date,
                    'date_end': self.end_date,
                }

            # Create or update the item
            if existing_item:
                existing_item.write(vals)
            else:
                self.env['product.pricelist.item'].create(vals)

        # 4) Store reference to the pricelist
        if hasattr(self, 'pricelist_id'):
            self.pricelist_id = pricelist.id

        # 5) CRITICAL: Make the pricelist effective by one of these methods:

        # Option A: Set as website pricelist if this is for e-commerce
        website = self.env['website'].get_current_website()
        if website:
            # Either set as the default pricelist
            website.pricelist_id = pricelist.id

            # Or add to the website's selectable pricelists
            website.pricelist_ids = [(4, pricelist.id)]
        self.message_post(body=_(
            "Discount applied to %s products via pricelist '%s'. "
            "The pricelist has been set as the website default pricelist.",
            len(self.product_tags), pricelist.name
        ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Discount applied and activated for %s products.', len(self.product_tags)),
                'sticky': False,
                'type': 'success',
            }
        }

    def action_remove_campaign_discount(self):
        """
        Remove the campaign discount and restore original pricing.
        """
        self.ensure_one()
        pricelist_name = f"Campaign {self.name} Discount"
        pricelist = self.env['product.pricelist'].search([
            ('name', '=', pricelist_name),
        ], limit=1)

        if pricelist:
            # 1) Remove pricelist from website if it was set
            website = self.env['website'].get_current_website()
            if website and website.pricelist_id.id == pricelist.id:
                # Reset to the default pricelist
                default_pricelist = self.env.ref('product.list0', raise_if_not_found=False)
                if default_pricelist:
                    website.pricelist_id = default_pricelist.id

            # 2) Remove from website's selectable pricelists
            if website and pricelist in website.pricelist_ids:
                website.pricelist_ids = [(3, pricelist.id)]

            # 3) Remove pricelist from any partners that might be using it
            partners = self.env['res.partner'].search([
                ('property_product_pricelist', '=', pricelist.id)
            ])
            if partners:
                default_pricelist = self.env.ref('product.list0', raise_if_not_found=False)
                if default_pricelist:
                    partners.write({'property_product_pricelist': default_pricelist.id})

            # 4) Remove the pricelist items
            items = self.env['product.pricelist.item'].search([
                ('pricelist_id', '=', pricelist.id),
                ('product_id', 'in', self.product_tags.ids),
            ])
            if items:
                items.unlink()

            # 5) Deactivate the pricelist
            pricelist.active = False

            self.message_post(body=_(
                "Campaign discount removed. Pricelist '%s' has been deactivated and removed from website/customers.",
                pricelist.name
            ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Discount removed and original pricing restored.'),
                'sticky': False,
                'type': 'success',
            }
        }




    def _compute_show_alerts(self):
        for rec in self:
            rec.show_canceled_alert = rec.status == 'canceled'
            rec.show_completed_alert = rec.status == 'completed'


    def _compute_campaign_stats(self):
        """Compute campaign statistics for dashboard."""
        for campaign in self:
            links = self.env['link.tracker'].search([('campaign_id1', '=', campaign.id)])
            clicks = links.mapped('link_click_ids')

            campaign.click_count = len(clicks)
            campaign.unique_click_count = len(set(clicks.mapped('ip')))

            sales = clicks.mapped('sale_id')
            campaign.total_sales = len(sales)
            campaign.total_revenue = sum(sales.mapped('amount_total'))
            campaign.conversion_rate = (
                    campaign.total_sales / campaign.click_count * 100) if campaign.click_count else 0

    @api.depends('cost_details_ids.amount')
    def _update_total_cost(self):
        """Update the total cost based on cost detail records."""
        for campaign in self:
            campaign.cost = sum(campaign.cost_details_ids.mapped('amount'))

    def _compute_record_color(self):
        for rec in self:
            # Example: assign color index based on status
            if rec.status == 'draft':
                rec.record_color = 1
            elif rec.status == 'running':
                rec.record_color = 2
            elif rec.status == 'completed':
                rec.record_color = 3
            elif rec.status == 'canceled':
                rec.record_color = 4
            else:
                rec.record_color = 0

    @api.onchange('product_tags')
    def _onchange_product_tags(self):
        """
        When products are selected, automatically find and add their
        corresponding images to image_ids
        """
        if not self.product_tags:
            return

        # Find all image records for the selected products
        product_ids = self.product_tags.ids
        image_records = self.env['image.model'].search([
            ('description', 'in', [str(pid) for pid in product_ids])
        ])

        # Add the found images to image_ids without duplicates
        if image_records:
            current_image_ids = self.image_ids.ids
            self.image_ids = [(4, img.id) for img in image_records if img.id not in current_image_ids]

    @api.model
    def _cron_check_completion(self):
        """Cron job to check if campaigns are completed based on end_date."""
        today = fields.Date.today()
        campaigns = self.search([
            ('status', '=', 'running'),
            ('end_date', '<=', today)
        ])
        for campaign in campaigns:
            campaign.action_set_completed()
            campaign.message_post(body=_("Campaign automatically marked as completed by the system."))

    @api.depends('product_tags')
    def _compute_product_links(self):
        """Compute product links for the campaign."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for campaign in self:
            product_links = [
                f"{base_url}/shop/product/{p.product_tmpl_id.id}" for p in self.env['product.product'].search([
                    ('is_published', '=', True),
                    ('id', 'in', campaign.product_tags.ids)
                ])
            ]
            campaign.product_links = "\n".join(product_links)

    def action_set_running(self):
        """Change campaign status to 'running' and validate dates."""
        for record in self:
            if not record.start_date or not record.end_date:
                raise UserError(_("A campaign must have both start and end dates before it can be set to running."))

            has_content = any([
                record.email_ids,
                record.x_ids,
                record.instagram_ids,
                record.facebook_ids
            ])

            if not has_content:
                raise UserError(_("Cannot start a campaign without any content. Please generate at least one post."))

            record.status = 'running'
            record.message_post(body=_("Campaign status changed to 'Running'"))

    def action_set_completed(self):
        """Mark the campaign as completed."""
        for record in self:
            if record.status != 'running':
                raise UserError(_("Only running campaigns can be marked as completed."))
            record.action_remove_campaign_discount()
            record.status = 'completed'
            record.message_post(body=_("Campaign marked as 'Completed'"))

    def action_set_canceled(self):
        """Cancel the campaign."""
        for record in self:
            if record.status == 'completed':
                raise UserError(_("Completed campaigns cannot be canceled."))
            record.status = 'canceled'
            record.message_post(body=_("Campaign was canceled."))

    def action_reset_to_draft(self):
        """Reset campaign to draft status."""
        for record in self:
            if record.status == 'completed':
                raise UserError(_("Completed campaigns cannot be reset to draft."))
            record.status = 'draft'
            record.message_post(body=_("Campaign reset to 'Draft' status."))

    @api.model
    def create(self, vals):
        """Override create to ensure new campaigns start in draft status."""
        if 'status' not in vals:
            vals['status'] = 'draft'
        return super(MarketingCampaign, self).create(vals)

    def get_status_info(self):
        """Get information about the current status of the campaign."""
        self.ensure_one()
        status_info = {
            'draft': {
                'description': _('Campaign is in preparation'),
                'next_actions': [_('Set to Running'), _('Cancel')],
                'color': 'gray'
            },
            'running': {
                'description': _('Campaign is currently active'),
                'next_actions': [_('Mark as Completed'), _('Cancel')],
                'color': 'green'
            },
            'completed': {
                'description': _('Campaign has successfully finished'),
                'next_actions': [],
                'color': 'blue'
            },
            'canceled': {
                'description': _('Campaign was terminated before completion'),
                'next_actions': [_('Reset to Draft')],
                'color': 'red'
            }
        }
        return status_info.get(self.status, {})

    def action_confirm(self):
        """Confirm the campaign by setting it to running."""
        return self.action_set_running()

    @api.onchange('start_date', 'end_date')
    def check_date_validity(self):
        """Validate campaign dates."""
        s = self.start_date
        e = self.end_date
        if isinstance(s, date) and isinstance(e, date):
            if e <= s:
                raise UserError(_("The end date must be greater than the start date"))
            if s < date.today():
                raise UserError(_("The start date must be greater than today's date"))

    @api.depends('start_date', 'end_date', 'email_ids', 'x_ids', 'instagram_ids', 'facebook_ids')
    def _compute_post_frequency(self):
        """Compute post frequency based on campaign duration and content count."""
        for record in self:
            s = record.start_date
            e = record.end_date
            if isinstance(s, date) and isinstance(e, date):
                num_weeks = (e - s).days / 7
            else:
                num_weeks = 0
            total_posts = sum([
                len(record.email_ids),
                len(record.x_ids),
                len(record.instagram_ids),
                len(record.facebook_ids)
            ])
            if int(num_weeks) > 0:
                record.post_frequency = f"{floor(total_posts / num_weeks)} per week"
            else:
                record.post_frequency = f"{total_posts} this week"

    def generate_tracked_link(self, original_url, medium, source):
        """
        Generate a tracked link for this campaign
        :param original_url: The URL to track
        :param medium: The UTM medium (e.g., 'email', 'social')
        :param source: The UTM source (e.g., 'facebook', 'twitter')
        :return: The shortened tracking URL
        """
        self.ensure_one()

        # Find or create UTM records
        utm_medium = self.env['utm.medium'].search([('name', '=', medium)], limit=1)
        if not utm_medium:
            utm_medium = self.env['utm.medium'].create({'name': medium})

        utm_source = self.env['utm.source'].search([('name', '=', source)], limit=1)
        if not utm_source:
            utm_source = self.env['utm.source'].create({'name': source})

        # Create the tracked link
        tracked_link = self.env['link.tracker'].create({
            'url': original_url,
            'campaign_id1': self.id,
            'source_id': utm_source.id,
            'medium_id': utm_medium.id
        })

        return tracked_link.short_url

    def get_email_publish_dates(self):
        """Get all email publish dates for this campaign."""
        self.ensure_one()
        email_records = self.env['social.email'].search([('campaign_id', '=', self.id)])
        publish_dates = email_records.mapped('publish_date')
        return [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

    def get_instagram_publish_dates(self):
        """Get all Instagram publish dates for this campaign."""
        self.ensure_one()
        instagram_records = self.env['social.instagram'].search([('campaign_id', '=', self.id)])
        publish_dates = instagram_records.mapped('publish_date')
        return [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

    def get_x_publish_dates(self):
        """Get all X (Twitter) publish dates for this campaign."""
        self.ensure_one()
        x_records = self.env['social.x'].search([('campaign_id', '=', self.id)])
        publish_dates = x_records.mapped('publish_date')
        return [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

    def get_facebook_publish_dates(self):
        """Get all Facebook publish dates for this campaign."""
        self.ensure_one()
        facebook_records = self.env['social.facebook'].search([('campaign_id', '=', self.id)])
        publish_dates = facebook_records.mapped('publish_date')
        return [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

    def extract_json_content(self, text):
        """Extracts the JSON content by removing characters before the first '{' and after the last '}'."""
        start_index = text.find('{')
        end_index = text.rfind('}')
        if start_index != -1 and end_index != -1:
            return text[start_index:end_index + 1]
        return ""

    def generate_email_prompt(self, context, tags):
        """Generate prompt for email content creation."""
        config = self.env['ir.config_parameter'].sudo()
        logo = config.get_param('Logo')
        company_name = self.company_id.name if self.company_id else "our company"
        images = ", ".join(self.image_ids.mapped('urldes')) if self.image_ids else "no images"
        links = ", ".join(self.link_ids.mapped('urldes')) if self.link_ids else "no links"
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        onlineShop = f"{base_url}/shop/"
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Generate tracked links for all products
        tracked_product_links = []
        if self.product_tags:
            for product in self.product_tags:
                product_url = f"{base_url}/shop/product/{product.product_tmpl_id.id}"
                tracked_url = self.generate_tracked_link(product_url, 'Email', 'Email')
                tracked_product_links.append(f"- {product.name}: {tracked_url}")

        # Discount information
        discount_info = "No active discount"
        if hasattr(self, 'apply_discount') and self.apply_discount:
            discount_type_text = "percentage" if self.discount_type == 'percent' else "fixed amount"
            discount_info = f"Active discount: {self.discount_value} {discount_type_text}"

        # Format product information
        if tracked_product_links:
            product_list = "\n".join([
                f"{product.name} ({product.description or 'No description'})"
                for product in self.product_tags
            ])
            product_links = "\n".join(tracked_product_links)
        else:
            product_list = "no specific products"
            product_links = "no product links"

        start_date1 = self.start_date
        end_date1 = self.end_date
        today = date.today()
        date_with_content_list = self.get_email_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"

        prompt_template = f"""
        You are an AI Email Marketing Assistant. Your task is to generate a JSON-formatted marketing email with HTML content that is engaging, persuasive, and aligned with the given campaign details.

    **Campaign Details:**
    - **Url logo of the company:** {logo}
    - **Start Date:** {start_date1}
    - **End Date:** {end_date1}
    - **Context:** {context}
    - **Tags:** {tags}
    - **Company Name:** {company_name}
    - **Product Tags:** {product_list}
    - **The Only Products link to our store**: {product_links}
    - **Content Strategy:** {content_strategy}
    - **Avoid Posting On:** {date_with_content_str}
    - **The Only Images**: {images}
    - **Just the raw link dont change them The Only Links**: {links}
    - **The Date of Today:** {today}
    - **Link to our Online Shop:** {onlineShop}
    - **Discount Information:** {discount_info}

    **Instructions:**
    - Craft a **compelling subject line** that encourages email opens.
    - Choose a **posting date and time** that maximizes audience engagement. Format: `YYYY-MM-DD HH:MM:SS`.
    - Design a **responsive HTML email template** with appropriate styling.
    - Include a professional header with the company name or logo placeholder.
    - Personalize the **greeting** using `{{name}}` as a placeholder (e.g., "Dear {{name}},").
    - Write an engaging **introduction** that captures attention and sets the stage.
    - Highlight key **details**, including features, benefits, and unique selling points of the product or service.
    - Include a **strong call-to-action (CTA)** with an attractive button.
    - End with a **friendly and professional closing** that reinforces brand credibility.
    - **- If there's an active discount, emphasize this prominently in the email as a special offer or sale.
    - Add a footer with unsubscribe option and company details.

    **Expected JSON Output Format:**
    ```json
    {{
        "subject_line": "<A compelling subject line>",
        "date_of_post": "<YYYY-MM-DD HH:MM:SS>",
        "html_content": "<Complete HTML email content with inline CSS styling>"
    }}
    ```
        """
        return prompt_template

    def action_generate_email_content(self):
        """Generate AI-powered email content and save it as a new record in the social.email model."""
        config = self.env['ir.config_parameter'].sudo()
        GOOGLE_API_KEY = config.get_param('GOOGLE_API_KEY')
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        email_prompt = self.generate_email_prompt(context, tags)
        try:
            gen = genai.GenerativeModel('gemini-2.0-flash')
            response = gen.generate_content(email_prompt)
            try:
                r = self.extract_json_content(response.text)
                email_data = json.loads(r)
            except json.JSONDecodeError as e:
                raise UserError(_("Invalid JSON response from AI model: %s", str(e)))

            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(email_data.get("date_of_post"), format)
            self.env['social.email'].with_context(mail_no_track=True).create({
                'campaign_id': self.id,
                'name': email_data.get("subject_line", ""),
                'publish_date': date_object,
                'content': email_data.get("html_content", "").strip(),
            })

            self.message_post(body=_("New AI-generated email content has been created successfully."))
        except Exception as e:
            self.message_post(body=_("Error generating email content: %s", str(e)))
            raise UserError(_("Error generating email content: %s", str(e)))

    def generate_facebook_prompt(self, context, tags):
        """Generate prompt for Facebook content creation."""
        company_name = self.company_id.name if self.company_id else "our company"
        content_strategy = self.content_strategy if self.content_strategy else "general"
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        links = ", ".join(self.link_ids.mapped('urldes')) if self.link_ids else "no links"

        # Generate tracked links for all products
        tracked_product_links = []
        if self.product_tags:
            for product in self.product_tags:
                product_url = f"{base_url}/shop/product/{product.product_tmpl_id.id}"
                tracked_url = self.generate_tracked_link(product_url, 'social', 'Facebook')
                tracked_product_links.append(f"- {product.name}: {tracked_url}")

        # Discount information
        discount_info = "No active discount"
        if hasattr(self, 'apply_discount') and self.apply_discount:
            discount_type_text = "percentage" if self.discount_type == 'percent' else "fixed amount"
            discount_info = f"Active discount: {self.discount_value} {discount_type_text}"

        # Format product information
        if tracked_product_links:
            product_list = "\n".join([
                f"{product.name} ({product.description or 'No description'})"
                for product in self.product_tags
            ])
            product_links = "\n".join(tracked_product_links)
        else:
            product_list = "no specific products"
            product_links = "no product links"

        start_date1 = self.start_date
        end_date1 = self.end_date
        today = date.today()
        date_with_content_list = self.get_facebook_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"

        prompt_template = f"""
        You are a **Social Media Marketing Assistant**. Your task is to create a **highly engaging Facebook post** that aligns with the marketing campaign details and drives audience interaction.

        ### **Campaign Details**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_list}
        - **The Only product links to our store:** {product_links}
        - **Content Strategy:** {content_strategy}
        - **Avoid Posting On:** {date_with_content_str}
        - **The Only Links**: {links}
        - **The Date of Today:** {today}
        - **Link to our Online Shop:** {base_url}/shop/
        - **Discount Information:** {discount_info}

        ### **Post Requirements**
        - **Headline:** Craft an attention-grabbing, scroll-stopping headline.
        - **Body Text:** Create an engaging post using a mix of compelling copy and relevant emojis 🎯🔥.
        - **Call-to-Action (CTA):** Encourage users to take action (e.g., visit a website, comment, share, or make a purchase).
        - **Hashtags:** Include strategic and trending hashtags to maximize reach and visibility.
        - **- If there's an active discount, emphasize this prominently in the post as a special offer or sale.

        Please return the Facebook post **as a structured JSON object** in the following format:

        ```json
        {{
            "headline": "<Catchy headline>",
            "body_text": "<Engaging post with emojis include the links here>",
            "call_to_action": "<Clear CTA>",
            "hashtags": "<Relevant hashtags>",
            "suggested_post_date": "<YYYY-MM-DD HH:MM:SS>",
            "media_suggestion": "<Optional: Image/video idea>"
        }}
        ```
        """
        return prompt_template

    def action_generate_facebook_content(self):
        """Generate AI-powered Facebook content and save it as a new record."""
        config = self.env['ir.config_parameter'].sudo()
        GOOGLE_API_KEY = config.get_param('GOOGLE_API_KEY')

        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        facebook_prompt = self.generate_facebook_prompt(context, tags)

        try:
            gen = genai.GenerativeModel('gemini-2.0-flash')
            response = gen.generate_content(facebook_prompt)
            try:
                r = self.extract_json_content(response.text)
                facebook_data = json.loads(r)
            except json.JSONDecodeError as e:
                raise UserError(_("Invalid JSON response from AI model: %s", str(e)))

            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(facebook_data.get("suggested_post_date"), format)
            fb_post = self.env['social.facebook'].create({
                'campaign_id': self.id,
                'name': facebook_data.get("headline", ""),
                'publish_date': date_object,
                'content': f"""
                    {facebook_data.get("body_text", "")}
                    {facebook_data.get("call_to_action", "")}
                    {facebook_data.get("hashtags", "")}
                """.strip(),
            })

            if self.image_ids:
                fb_post.write({
                    'image_ids': [(6, 0, self.image_ids.ids)]
                })

            self.message_post(body=_("New AI-generated Facebook content has been created successfully."))
        except Exception as e:
            self.message_post(body=_("Error generating Facebook content: %s", str(e)))
            raise UserError(_("Error generating Facebook content: %s", str(e)))

    def generate_instagram_prompt(self, context, tags):
        """Generate prompt for Instagram content creation."""
        company_name = self.company_id.name if self.company_id else "our company"
        content_strategy = self.content_strategy if self.content_strategy else "general"
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        onlineShop = self.generate_tracked_link(f"{base_url}/shop/", 'social', 'Instagram')
        links = ", ".join(self.link_ids.mapped('urldes')) if self.link_ids else "no links"

        # Generate tracked links for all products
        tracked_product_links = []
        if self.product_tags:
            for product in self.product_tags:
                product_url = f"{base_url}/shop/product/{product.product_tmpl_id.id}"
                tracked_url = self.generate_tracked_link(product_url, 'social', 'Instagram')
                tracked_product_links.append(f"- {product.name}: {tracked_url}")

        # Discount information
        discount_info = "No active discount"
        if hasattr(self, 'apply_discount') and self.apply_discount:
            discount_type_text = "percentage" if self.discount_type == 'percent' else "fixed amount"
            discount_info = f"Active discount: {self.discount_value} {discount_type_text}"

        # Format product information
        if tracked_product_links:
            product_list = "\n".join([
                f"{product.name} ({product.description or 'No description'})"
                for product in self.product_tags
            ])
            product_links = "\n".join(tracked_product_links)
        else:
            product_list = "no specific products"
            product_links = "no product links"

        start_date1 = self.start_date
        end_date1 = self.end_date
        today = date.today()
        date_with_content_list = self.get_instagram_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"

        prompt_template = f"""
        You are a **Social Media Marketing Assistant AI**. Your role is to generate a **high-converting Instagram post** for the campaign described below. The post should follow best practices for engagement, storytelling, and brand alignment.

        ### 📋 Campaign Details:
        - **Company Name:** {company_name}
        - **Campaign Start Date:** {start_date1}
        - **Campaign End Date:** {end_date1}
        - **Campaign Context:** {context}
        - **Content Strategy:** {content_strategy}
        - **Tags:** {tags}
        - **Avoid Posting On:** {date_with_content_str}
        - **Today's Date:** {today}
        - **Discount Information:** {discount_info}

        ---

        ### 🛍️ Products & Links:
        - **Featured Products:**  
        {product_list}

        - **Required Product Links (must be included):**  
        {product_links}

        - **Online Shop (include link if relevant):** {onlineShop}
        - **Additional Campaign Links:** {links}
        - **- If there's an active discount, emphasize this prominently in the post as a special offer or sale.

        ### 🧠 Your Output Must Include:
        Return your response in the **following strict JSON format** with high-quality content:
        
        ```json
        {{
          "headline": "<Catchy, bold headline that grabs attention>",
          "caption": "<Story-driven caption that connects emotionally, includes emojis 🎯🔥🚀, and aligns with the brand voice>",
          "call_to_action": "<Interactive CTA such as 'Tag a friend', 'DM us for details', etc.>",
          "Links":"<Put the links here in presentable manner to put directly in the description of the post>",
          "hashtags": "<A list of 5–10 relevant and trending hashtags>",
          "suggested_post_date": "<A future date (YYYY-MM-DD HH:MM:SS) that avoids the listed blocked dates>",
          "media_suggestion": "<Optional: Describe an ideal image or video that matches the post theme>"
        }}
        ```
        """
        return prompt_template

    def action_generate_instagram_content(self):
        """Generate AI-powered Instagram content and save it as a new record."""
        config = self.env['ir.config_parameter'].sudo()

        GOOGLE_API_KEY = config.get_param('GOOGLE_API_KEY')
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        instagram_prompt = self.generate_instagram_prompt(context, tags)

        try:
            gen = genai.GenerativeModel('gemini-2.0-flash')
            response = gen.generate_content(instagram_prompt)
            try:
                r = self.extract_json_content(response.text)
                instagram_data = json.loads(r)
            except json.JSONDecodeError as e:
                raise UserError(_("Invalid JSON response from AI model: %s", str(e)))

            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(instagram_data.get("suggested_post_date"), format)
            ig_post = self.env['social.instagram'].create({
                'campaign_id': self.id,
                'name': instagram_data.get("headline", ""),
                'publish_date': date_object,
                'caption': f"""
                    {instagram_data.get("caption", "")}
                    {instagram_data.get("call_to_action", "")}
                    {instagram_data.get("Links", "")}
                    {instagram_data.get("hashtags", "")}
                """.strip(),
            })

            if self.image_ids:
                ig_post.write({
                    'image_ids': [(6, 0, self.image_ids.ids)]
                })

            self.message_post(body=_("New AI-generated Instagram content has been created successfully."))
        except Exception as e:
            self.message_post(body=_("Error generating Instagram content: %s", str(e)))
            raise UserError(_("Error generating Instagram content: %s", str(e)))

    def generate_x_prompt(self, context, tags):
        """Generate prompt for Twitter (X) content creation."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        onlineShop = f"{base_url}/shop/"
        company_name = self.company_id.name if self.company_id else "our company"
        content_strategy = self.content_strategy if self.content_strategy else "general"
        links = ", ".join(self.link_ids.mapped('urldes')) if self.link_ids else "no links"

        # Generate tracked links for all products
        tracked_product_links = []
        if self.product_tags:
            for product in self.product_tags:
                product_url = f"{base_url}/shop/product/{product.product_tmpl_id.id}"
                tracked_url = self.generate_tracked_link(product_url, 'social', 'Twitter')
                tracked_product_links.append(f"- {product.name}: {tracked_url}")

        # Discount information
        discount_info = "No active discount"
        if hasattr(self, 'apply_discount') and self.apply_discount:
            discount_type_text = "percentage" if self.discount_type == 'percent' else "fixed amount"
            discount_info = f"Active discount: {self.discount_value} {discount_type_text}"
        # Format product information
        if tracked_product_links:
            product_list = "\n".join([
                f"{product.name} ({product.description or 'No description'})"
                for product in self.product_tags
            ])
            product_links = "\n".join(tracked_product_links)
        else:
            product_list = "no specific products"
            product_links = "no product links"

        start_date1 = self.start_date
        end_date1 = self.end_date
        date_with_content_list = self.get_x_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        today = date.today()

        prompt_template = f"""
        You are a **Twitter (X) Marketing Assistant**. Your task is to create a **highly engaging tweet** that aligns with the marketing campaign details and encourages user engagement.

        ### **Campaign Details**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_list}
        - **The Only product links to our store:** {product_links}
        - **Content Strategy:** {content_strategy}
        - **Avoid Posting On:** {date_with_content_str}
        - **The Only Links**: {links}
        - **The Date of Today:** {today}
        - **Link to our Online Shop:** {onlineShop}
        - **Discount Information:** {discount_info}

        ### **Tweet Requirements**
        - **Text Length:** Ensure the tweet is within **280 characters**.
        - **Emojis & Hashtags:** Use a mix of engaging emojis (🔥🚀) and relevant hashtags.
        - **Call-to-Action (CTA):** Encourage user interaction (e.g., "Retweet if you agree!", "Drop your thoughts below 👇").
        - **Media:** If applicable, suggest an image or GIF.
        - **Tone & Style:** Ensure the tweet is **witty, concise, and brand-aligned**.
        - **Make sure to add the product links** in the tweet.
        - **- If there's an active discount, emphasize this prominently in the post as a special offer or sale.

        Please return the tweet in the following structured JSON format:

        ```json
        {{  
            "title": "<Tweet Title>",
            "tweet_text": "<Engaging tweet within 280 characters>",
            "hashtags": ["#example", "#marketing"],
            "suggested_send_time": "<YYYY-MM-DD HH:MM:SS>"
        }}
        """
        return prompt_template

    def action_generate_x_content(self):
        """Generate AI-powered Twitter (X) content and save it as a new record."""
        config = self.env['ir.config_parameter'].sudo()
        GOOGLE_API_KEY = config.get_param('GOOGLE_API_KEY')
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        x_prompt = self.generate_x_prompt(context, tags)

        try:
            gen = genai.GenerativeModel('gemini-2.0-flash')
            response = gen.generate_content(x_prompt)

            try:
                r = self.extract_json_content(response.text)
                x_data = json.loads(r)
            except json.JSONDecodeError as e:
                raise UserError(_("Invalid JSON response from AI model: %s", str(e)))

            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(x_data.get("suggested_send_time"), format)
            x_post = self.env['social.x'].create({
                'campaign_id': self.id,
                'name': x_data.get("title", ""),
                'publish_date': date_object,
                'caption': x_data.get("tweet_text", ""),
            })
            if self.image_ids:
                x_post.write({
                    'image_ids': [(6, 0, self.image_ids.ids)]
                })

            self.message_post(body=_("New AI-generated Twitter content has been created successfully."))
        except Exception as e:
            self.message_post(body=_("Error generating Twitter content: %s", str(e)))
            raise UserError(_("Error generating Twitter content: %s", str(e)))