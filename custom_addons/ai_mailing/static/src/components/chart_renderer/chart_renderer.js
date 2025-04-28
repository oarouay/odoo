/** @odoo-module */

import { registry } from "@web/core/registry"
import { loadJS } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";
const { Component, onWillStart, useRef, onMounted, onPatched } = owl

export class ChartRenderer extends Component {
    setup() {
        this.chartRef = useRef("chart");
        this.chart = null;
        this.orm = useService("orm");
        this.chartData = null;
        onWillStart(async () => {
            await loadJS("https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js")
            await this.fetchChartData();
        })
        onMounted(() => this.renderChart())

        onPatched(() => {
            if (this.props.campaignId !== this.lastCampaignId ||
                this.props.chartInterval !== this.lastChartInterval ||
                this.props.socialMediaDateRange !== this.lastSocialMediaDateRange ||
                this.props.budgetDateRange !== this.lastbudgetDateRange ||
                this.props.performanceMetric !== this.lastperformanceMetric ||
                this.props.chartDateRange !== this.lastChartDateRange) {
                this.fetchChartData().then(() => this.renderChart());
            }
        });
    }

    async fetchChartData() {
        // Store current campaign ID to detect changes
        this.lastCampaignId = this.props.campaignId;
        this.lastChartInterval = this.props.chartInterval;
        this.lastChartDateRange = this.props.chartDateRange;
        this.lastSocialMediaDateRange = this.props.socialMediaDateRange;
        this.lastperformanceMetric = this.props.performanceMetric;
        this.lastbudgetDateRange = this.props.budgetDateRange



        try {
            // Determine which data to fetch based on chart type
            let methodName = "get_default_chart_data";
            const domain = this.props.campaignId ? [['id', '=', this.props.campaignId]] : [];
            const params = [domain];
            switch (this.props.chartName) {
                case 'top_products_chart':
                    methodName = "get_top_products_data";
                    break;
                case 'budget_vs_performance_chart':
                    methodName = "get_campaign_roi_comparison_data";
                    if (this.props.budgetDateRange) {
                        params.push(this.props.budgetDateRange);
                    }
                    break;
                case 'social_media_performance_chart':
                    methodName = "get_clicks_sales_by_source";
                    if (this.props.socialMediaDateRange) {
                        params.push(this.props.socialMediaDateRange);
                    }
                    break;
                case 'clicks_sales_trend_chart':
                    methodName = "get_clicks_and_sales_over_time";
                    if (this.props.chartInterval) {
                        params.push(this.props.chartInterval);
                    }
                    if (this.props.chartDateRange) {
                        params.push(this.props.chartDateRange);
                    }
                    break;
            }
            // Fetch data from backend
            this.chartData = await this.orm.call(
                "marketing.campaign",
                methodName,
                params
            );

            // Handle different response formats
            if (this.chartData && this.chartData.chart_data) {
                this.chartData = this.chartData.chart_data;
            }

            console.log(`Fetched ${methodName} data:`, this.chartData);
        } catch (error) {
            console.error("Error fetching chart data:", error);
            // Use default data if fetch fails
            this.chartData = {
                labels: ['No Data Available'],
                datasets: [{
                    label: 'No Data',
                    data: [100],
                    backgroundColor: ['#cccccc']
                }]
            };
        }
    }

    renderChart() {
        // Destroy previous chart if it exists
        if (this.chart) {
            this.chart.destroy();
        }

        // Use fetched data or fallback to default
        const data = this.chartData || {
            labels: ['Red', 'Blue', 'Yellow'],
            datasets: [
                {
                    label: 'My First Dataset',
                    data: [300, 50, 100],
                    hoverOffset: 4
                }
            ]
        };

        // Make sure Chart.js is available
        if (!window.Chart) {
            console.error("Chart.js is not loaded!");
            return;
        }

        // Map Odoo chart types to Chart.js types
        const chartTypeMap = {
            'doughnut': 'doughnut',
            'pie': 'pie',
            'bar': 'bar',
            'line': 'line'
        };

        // Use the mapped type or fallback to 'bar'
        const chartType = chartTypeMap[this.props.type] || 'bar';

        // Create chart configuration
        const config = {
            type: chartType,
            data: data,
            options: {
                responsive: true,
                animation: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    title: {
                        display: true,
                        text: this.props.title,
                        position: 'bottom'
                    }
                }
            }
        };

        try {
            this.chart = new Chart(this.chartRef.el, config);
        } catch (error) {
            console.error("Error creating chart:", error);
            // Try with fallback chart type
            config.type = 'bar';
            this.chart = new Chart(this.chartRef.el, config);
        }
    }
}

ChartRenderer.template = "ai_mailing.ChartRenderer"