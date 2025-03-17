from dateutil.utils import today

from odoo.exceptions import UserError

from odoo import models, fields, api
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, date
import os
import json
from math import floor

load_dotenv()

class MarketingCampaign(models.Model):
    _name = "marketing.campaign"
    _description = "Marketing Campaign"
    _inherit = ["mail.thread"]



    company_id = fields.Many2one('res.company', string='Company', index=True, default=lambda self: self.env.company)

    # Campaign Basic Information
    name = fields.Char(string="Campaign Name", required=True)
    campaign_type = fields.Selection([
        ('social_media', 'Social Media'),
        ('email_marketing', 'Email Marketing'),
        ('ads', 'Advertising')
    ], string="Campaign Type", required=True)
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")
    status = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled')
    ], string="Status", default='draft')

    content_strategy = fields.Selection([
        ('engagement', 'Engagement'),
        ('sales', 'Sales'),
        ('awareness', 'Brand Awareness')
    ], string="Content Strategy")
    post_frequency = fields.Char(string="Post Frequency",compute="_compute_post_frequency", store=True, default="")
    context = fields.Text(string="Context")
    tag_ids = fields.Many2many('prompt.tag', string='Tags')
    image_ids = fields.Many2many('image.model', string='Images')


    email_ids = fields.One2many('social.email', 'campaign_id', string="Emails")
    x_ids = fields.One2many('social.x', 'campaign_id', string="Tweets")
    instagram_ids = fields.One2many('social.instagram', 'campaign_id', string="Instagram Posts")
    facebook_ids = fields.One2many('social.facebook', 'campaign_id', string="Facebook Posts")

    # AI-Generated Email Content
    optional_product_ids = fields.Many2many('product.product', string='Optional Products')
    optional_product_tags = fields.Many2many(
        'product.product',
        relation='marketing_campaign_product_tags_rel',
        column1='campaign_id',
        column2='product_id',
        string="Product Tags(optional)",
        compute="_compute_optional_product_tags",
        store=True
    )

    def action_set_running(self):
        """Change campaign status to 'running' and validate dates."""
        for record in self:
            # Validate that the campaign has a start and end date
            if not record.start_date or not record.end_date:
                raise UserError("A campaign must have both start and end dates before it can be set to running.")

            # Check if there's at least one content item
            has_content = any([
                record.email_ids,
                record.x_ids,
                record.instagram_ids,
                record.facebook_ids
            ])

            if not has_content:
                raise UserError("Cannot start a campaign without any content. Please generate at least one post.")

            record.status = 'running'
            record.message_post(body="Campaign status changed to 'Running'")

    def action_set_completed(self):
        """Mark the campaign as completed."""
        for record in self:
            # Only running campaigns can be completed
            if record.status != 'running':
                raise UserError("Only running campaigns can be marked as completed.")

            record.status = 'completed'
            record.message_post(body="Campaign marked as 'Completed'")

    def action_set_canceled(self):
        """Cancel the campaign."""
        for record in self:
            # Can't cancel completed campaigns
            if record.status == 'completed':
                raise UserError("Completed campaigns cannot be canceled.")

            record.status = 'canceled'
            record.message_post(body="Campaign was canceled.")

    def action_reset_to_draft(self):
        """Reset campaign to draft status."""
        for record in self:
            # Completed campaigns can't be reset
            if record.status == 'completed':
                raise UserError("Completed campaigns cannot be reset to draft.")

            record.status = 'draft'
            record.message_post(body="Campaign reset to 'Draft' status.")

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
                'description': 'Campaign is in preparation',
                'next_actions': ['Set to Running', 'Cancel'],
                'color': 'gray'
            },
            'running': {
                'description': 'Campaign is currently active',
                'next_actions': ['Mark as Completed', 'Cancel'],
                'color': 'green'
            },
            'completed': {
                'description': 'Campaign has successfully finished',
                'next_actions': [],  # No further actions for completed campaigns
                'color': 'blue'
            },
            'canceled': {
                'description': 'Campaign was terminated before completion',
                'next_actions': ['Reset to Draft'],
                'color': 'red'
            }
        }

        return status_info.get(self.status, {})

    def can_generate_content(self):
        """Check if content can be generated for this campaign."""
        self.ensure_one()
        return self.status in ['draft', 'running']

    def action_confirm(self):
        """Confirm the campaign by setting it to running."""
        return self.action_set_running()


    @api.onchange('start_date','end_date')
    def check_date_validity(self):
        s = self.start_date
        e = self.end_date
        if isinstance(s, date) and isinstance(e, date):
            if e<=s :
                raise UserError("The end date must be greater than the start date")
            if s<date.today() :
                raise UserError("The start date must be greater than todays date")

    @api.depends('start_date','end_date','email_ids', 'x_ids', 'instagram_ids', 'facebook_ids')
    def _compute_post_frequency(self):
        for record in self:
            s=record.start_date
            e=record.end_date
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
                record.post_frequency = f"{floor(total_posts / num_weeks):} per week"
            else:
                record.post_frequency = f"{total_posts} this week"

    @api.depends("optional_product_ids")
    def _compute_optional_product_tags(self):
        for record in self:
            record.optional_product_tags = record.optional_product_ids

    def get_email_publish_dates(self):
        self.ensure_one()

        email_records = self.env['social.email'].search([
            ('campaign_id', '=', self.id)
        ])

        publish_dates = email_records.mapped('publish_date')

        publish_dates_str = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

        return publish_dates_str

    def get_instagram_publish_dates(self):

        self.ensure_one()


        email_records = self.env['social.instagram'].search([
            ('campaign_id', '=', self.id)
        ])
        publish_dates = email_records.mapped('publish_date')

        publish_dates_str = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

        return publish_dates_str

    def get_x_publish_dates(self):
        self.ensure_one()

        email_records = self.env['social.x'].search([
            ('campaign_id', '=', self.id)
        ])
        publish_dates = email_records.mapped('publish_date')

        publish_dates_str = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

        return publish_dates_str

    def get_facebook_publish_dates(self):
        self.ensure_one()

        email_records = self.env['social.facebook'].search([
            ('campaign_id', '=', self.id)
        ])
        publish_dates = email_records.mapped('publish_date')

        publish_dates_str = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in publish_dates if dt]

        return publish_dates_str

    def generate_email_prompt(self, context, tags):

        company_name = self.company_id.name if self.company_id else "our company"

        images = ", ".join(self.image_ids.mapped('urldes')) if self.image_ids else "no images"

        # Extract product tags or set a default
        product_tags = ", ".join(
            self.optional_product_tags.mapped('name')) if self.optional_product_tags else "products"

        # Extract content strategy or set a default
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Get campaign start and end dates
        start_date1 = self.start_date
        end_date1 = self.end_date

        #Todays Date
        today = date.today()
        print(today)

        # Get email publish dates and format as a string
        date_with_content_list = self.get_email_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        print(date_with_content_str)
        # Define the AI prompt
        prompt_template = f"""
        You are an AI Email Marketing Assistant. Your task is to generate a JSON-formatted marketing email with HTML content that is engaging, persuasive, and aligned with the given campaign details.

    **Campaign Details:**
    - **Start Date:** {start_date1}
    - **End Date:** {end_date1}
    - **Context:** {context}
    - **Tags:** {tags}
    - **Company Name:** {company_name}
    - **Product Tags:** {product_tags}
    - **Content Strategy:** {content_strategy}
    - **Avoid Posting On:** {date_with_content_str}
    - **The Only Images**: {images}
    - **The Date of Today:** {today}

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
    - Add a footer with unsubscribe option and company details.

    **Expected JSON Output Format:**
    ```json
    {{
        "subject_line": "<A compelling subject line>",
        "date_of_post": "<YYYY-MM-DD HH:MM:SS>",
        "html_content": "<Complete HTML email content with inline CSS styling>"
    }}
    ```

    **HTML Requirements:**
    - Create a clean, professional design with responsive layout
    - Use inline CSS for styling (no external stylesheets)
    - Ensure compatibility with major email clients
    - Include appropriate spacing, colors, and formatting
    - Create visually distinct sections for introduction, details, and CTA
    - Use appropriate HTML tags for semantic structure
    - Include placeholder text for images with descriptive alt text

    **Marketing Requirements:**
    - Follow a **persuasive marketing tone** tailored to the provided context and audience
    - Optimize for readability, engagement, and conversion
    - Ensure the response is a **valid JSON object** with no extraneous text or formatting
        """

        return prompt_template

    def extract_json_content(self,text):
        """Extracts the JSON content by removing characters before the first '{' and after the last '}'."""
        # Find the index of the first '{' and the last '}'
        start_index = text.find('{')
        end_index = text.rfind('}')

        # If both '{' and '}' are found, return the substring between them
        if start_index != -1 and end_index != -1:
            return text[start_index:end_index + 1]

        # If no valid JSON content is found, return an empty string
        return ""

    def action_generate_email_content(self):
        """Generate AI-powered email content and save it as a new record in the social.email model."""
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        email_prompt = self.generate_email_prompt(context, tags)

        try:
            # Generate content using the AI model
            gen = genai.GenerativeModel('gemini-1.5-flash')
            response = gen.generate_content(email_prompt)
            print(response)
            try:
                r=self.extract_json_content(response.text)
                email_data = json.loads(r)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                raise ValueError(f"Invalid JSON response from AI model: {str(e)}")
            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(email_data.get("date_of_post"), format)
            print(date_object)
            self.env['social.email'].create({
                'campaign_id': self.id,
                'name': email_data.get("subject_line",""),
                'publish_date':date_object,
                'content': f"""
                    {email_data.get("html_content", "")}
                """.strip(),  # Combine all parts of the email content
            })
            print(self.get_email_publish_dates())
            self.message_post(body="New AI-generated email content has been created successfully.")
        except Exception as e:
            self.message_post(body=f"Error generating email content: {str(e)}")

    def generate_facebook_prompt(self, context, tags):
        # Extract company details safely
        company_name = self.company_id.name if self.company_id else "our company"
        product_tags = ", ".join(
            self.optional_product_tags.mapped('name')) if self.optional_product_tags else "products"
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Get campaign start and end dates
        start_date1 = self.start_date
        end_date1 = self.end_date
        today=date.today()
        date_with_content_list = self.get_facebook_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        print(date_with_content_str)
        prompt_template = f"""
        You are a **Social Media Marketing Assistant**. Your task is to create a **highly engaging Facebook post** that aligns with the marketing campaign details and drives audience interaction.

        ### **Campaign Details**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_tags}
        - **Content Strategy:** {content_strategy}
        - **Avoid Posting On:** {date_with_content_str}
        - **The Date of Today:** {today}

        ### **Post Requirements**
        - **Headline:** Craft an attention-grabbing, scroll-stopping headline.
        - **Body Text:** Create an engaging post using a mix of compelling copy and relevant emojis 🎯🔥.
        - **Call-to-Action (CTA):** Encourage users to take action (e.g., visit a website, comment, share, or make a purchase).
        - **Hashtags:** Include strategic and trending hashtags to maximize reach and visibility.

        ### **Tone & Style**
        - Ensure the **tone aligns with {company_name}'s brand identity**.
        - Follow the **{content_strategy}** strategy for consistency across campaigns.
        - Adapt the post style for **maximum engagement on Facebook**.

        **Additional Considerations:**
        - Optimize post length for Facebook's algorithm (~40-80 words for engagement).
        - If relevant, suggest a high-quality image or video idea that enhances the post.
        - Ensure the post follows Facebook’s **best practices** for organic reach.

        Please return the Facebook post **as a structured JSON object** in the following format:

        ```json
        {{
            "headline": "<Catchy headline>",
            "body_text": "<Engaging post with emojis>",
            "call_to_action": "<Clear CTA>",
            "hashtags": "<Relevant hashtags>",
            "suggested_post_date": "<YYYY-MM-DD HH:MM:SS>",
            "media_suggestion": "<Optional: Image/video idea>"
        }}
        ```

        Ensure that the output is **valid JSON**, without any extra text or formatting outside of the JSON object.
        """

        return prompt_template

    def action_generate_facebook_content(self):
        """Generate AI-powered Facebook content and save it as a new record."""
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        facebook_prompt = self.generate_facebook_prompt(context, tags)

        try:
            gen = genai.GenerativeModel('gemini-1.5-flash')
            response = gen.generate_content(facebook_prompt)
            try:
                r = self.extract_json_content(response.text)
                facebook_data = json.loads(r)
                print(facebook_data)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                raise ValueError(f"Invalid JSON response from AI model: {str(e)}")
            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(facebook_data.get("suggested_post_date"), format)
            self.env['social.facebook'].create({
                'campaign_id': self.id,
                'name': facebook_data.get("headline", ""),
                'publish_date': date_object,
                'content': f"""
                                {facebook_data.get("body_text", "")}
                                {facebook_data.get("call_to_action", "")}
                                {facebook_data.get("hashtags", "")}
                            """.strip(),  # Combine all parts of the email content
            })

        except Exception as e:
            self.message_post(body=f"Error generating Facebook content: {str(e)}")

        self.message_post(body="New AI-generated Facebook content has been created successfully.")

    def generate_instagram_prompt(self, context, tags):

        company_name = self.company_id.name if self.company_id else "our company"
        product_tags = ", ".join(
            self.optional_product_tags.mapped('name')) if self.optional_product_tags else "products"
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Get campaign start and end dates
        start_date1 = self.start_date
        end_date1 = self.end_date
        today = date.today()
        # Get restricted posting dates
        date_with_content_list = self.get_instagram_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        print(date_with_content_str)
        prompt_template = f"""
        You are a **Social Media Marketing Assistant**. Your task is to create a **highly engaging Instagram post** that aligns with the marketing campaign details and drives audience interaction.

        ### **Campaign Details**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_tags}
        - **Content Strategy:** {content_strategy}
        - **Avoid Posting On:** {date_with_content_str}
        - **The Date of Today:** {today}

        ### **Post Requirements**
        - **Caption:** Write a compelling and engaging caption with a mix of storytelling and brand messaging.
        - **Emojis:** Use emojis 🎯🔥🚀 to make the post visually appealing and engaging.
        - **Call-to-Action (CTA):** Encourage interaction (e.g., "Tag a friend," "Swipe up," "DM us").
        - **Hashtags:** Include trending and relevant hashtags to increase reach.
        - **Image Idea (Optional):** Suggest an ideal image or video concept that fits the post.

        ### **Tone & Style**
        - Ensure the **tone aligns with {company_name}'s brand identity**.
        - Follow the **{content_strategy}** strategy for consistency across campaigns.
        - Adapt the post style for **maximum engagement on Instagram**.

        **Please return the Instagram post in the following structured JSON format:**

        ```json
        {{
            "headline": "<Catchy headline>",
            "caption": "<Engaging caption with emojis>",
            "call_to_action": "<Clear CTA>",
            "hashtags": "<Relevant hashtags>",
            "suggested_post_date": "<YYYY-MM-DD HH:MM:SS>",
            "media_suggestion": "<Optional: Image/video idea>"
        }}
        ```

        Ensure that the output is **valid JSON**, without any extra text or formatting outside of the JSON object.
        """

        return prompt_template

    def action_generate_instagram_content(self):
        """Generate AI-powered Instagram content and save it as a new record."""
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        instagram_prompt = self.generate_instagram_prompt(context, tags)

        print("Generated Instagram Prompt:\n", instagram_prompt)

        try:
            gen = genai.GenerativeModel('gemini-1.5-flash')
            response = gen.generate_content(instagram_prompt)
            try:
                r = self.extract_json_content(response.text)
                instagram_data = json.loads(r)
                print(instagram_data)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                raise ValueError(f"Invalid JSON response from AI model: {str(e)}")
            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(instagram_data.get("suggested_post_date"), format)
            self.env['social.instagram'].create({
                'campaign_id': self.id,
                'name': instagram_data.get("headline", ""),
                'publish_date': date_object,
                'caption': f"""
                                {instagram_data.get("caption", "")}
                                {instagram_data.get("call_to_action", "")}
                                {instagram_data.get("hashtags", "")}
                            """.strip(),  # Combine all parts of the email content
            })

        except Exception as e:
            self.message_post(body=f"Error generating Facebook content: {str(e)}")

        self.message_post(body="New AI-generated Facebook content has been created successfully.")

    def generate_x_prompt(self, context, tags):
        """Generate a structured and engaging Twitter (X) post prompt for AI."""

        # Extract company details safely
        company_name = self.company_id.name if self.company_id else "our company"
        product_tags = ", ".join(
            self.optional_product_tags.mapped('name')) if self.optional_product_tags else "products"
        content_strategy = self.content_strategy if self.content_strategy else "general"

        # Get campaign start and end dates
        start_date1 = self.start_date
        end_date1 = self.end_date

        # Get restricted posting dates
        date_with_content_list = self.get_x_publish_dates()
        date_with_content_str = ", ".join(date_with_content_list) if date_with_content_list else "None"
        today = date.today()
        print(date_with_content_str)

        # Define the AI prompt
        prompt_template = f"""
        You are a **Twitter (X) Marketing Assistant**. Your task is to create a **highly engaging tweet** that aligns with the marketing campaign details and encourages user engagement.

        ### **Campaign Details**
        - **Start Date:** {start_date1}
        - **End Date:** {end_date1}
        - **Context:** {context}
        - **Tags:** {tags}
        - **Company Name:** {company_name}
        - **Product Tags:** {product_tags}
        - **Content Strategy:** {content_strategy}
        - **Avoid Posting On:** {date_with_content_str}
        - **The Date of Today:** {today}

        ### **Tweet Requirements**
        - **Text Length:** Ensure the tweet is within **280 characters**.
        - **Emojis & Hashtags:** Use a mix of engaging emojis (🔥🚀) and relevant hashtags.
        - **Call-to-Action (CTA):** Encourage user interaction (e.g., "Retweet if you agree!", "Drop your thoughts below 👇").
        - **Media:** If applicable, suggest an image or GIF.
        - **Tone & Style:** Ensure the tweet is **witty, concise, and brand-aligned**.

        **Please return the tweet in the following structured JSON format:**

        ```json
        {{  
            "title": "<Tweet Title>"
            "tweet_text": "<Engaging tweet within 280 characters>",
            "hashtags": ["#example", "#marketing"],
            "suggested_send_time": "<YYYY-MM-DD HH:MM:SS>"
        }}
        ```

        Ensure that the output is **valid JSON**, without any extra text or formatting outside of the JSON object.
        """

        return prompt_template

    def action_generate_x_content(self):
        """Generate AI-powered Twitter (X) content and save it as a new record."""
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        context = self.context
        tags = ", ".join(self.tag_ids.mapped('name'))
        x_prompt = self.generate_x_prompt(context, tags)

        print("Generated Twitter Prompt:\n", x_prompt)

        try:
            gen = genai.GenerativeModel('gemini-1.5-flash')
            response = gen.generate_content(x_prompt)

            try:
                r = self.extract_json_content(response.text)
                x_data = json.loads(r)
                print(x_data)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                raise ValueError(f"Invalid JSON response from AI model: {str(e)}")

            format = "%Y-%m-%d %H:%M:%S"
            date_object = datetime.strptime(x_data.get("suggested_send_time"), format)
            print(date_object)
            self.env['social.x'].create({
                'campaign_id': self.id,
                'name': x_data.get("title", ""),
                'publish_date': date_object,
                'caption': x_data.get("tweet_text", ""),
            })

        except Exception as e:
            self.message_post(body=f"Error generating Twitter content: {str(e)}")

        self.message_post(body="New AI-generated Twitter content has been created successfully.")

