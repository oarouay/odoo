{
    "name" : "Generate Email with AI",
    "author" : "Arouay",
    "license" : "LGPL-3",
    "depends" : [
        'mail',
        'sale',
        'product',
        'mass_mailing',
        'website_sale',
        "utm",
                 ],
    "data" : [
        'security/security.xml',
        "security/ir.model.access.csv",
        "report/custom_layout.xml",
        "report/campagn_report_views.xml",
        "views/cost_views.xml",
        "views/calendar_views.xml",
        "views/dashboard_sales.xml",
        "views/mailing_ai_views.xml",
        "views/prompt_tag_views.xml",
        "views/social_views.xml",
        "views/cron_job.xml",
        "views/media_views.xml",
        "views/social_actions.xml",
        "views/menu_mailing.xml"
    ],
    'assets': {
        'web.assets_backend': [
            'ai_mailing/static/src/components/**/*.js',
            'ai_mailing/static/src/components/**/*.xml',
            'ai_mailing/static/src/components/**/*.scss',
        ],
    },
    "application": True,
    "installable": True
}