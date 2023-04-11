import json

from news_aggregator_service.aggregators.models.bing_news import NewsAnswerAPIResponse, NewsArticle


def test_bing_news_search_api_response_model():
    with open("tests/test_models/test_data/news_by_category_valid.json") as f:
        test_data = json.load(f)
        response = NewsAnswerAPIResponse(**test_data)
        assert response.total_estimated_matches == 36
        assert response.sort[0].id == "relevance"
        assert response.sort[0].is_selected == True
        assert response.sort[1].id == "date"
        assert response.sort[1].is_selected == False
        assert response.related_topics is None
        assert response.value is not None
        assert response.query_context.original_query == "Generative AI"
        assert len(response.value) == 10


def test_bing_news_article_model():
    with open("tests/test_models/test_data/news_article_valid.json") as f:
        test_article = json.load(f)
        article = NewsArticle(**test_article)
        assert (
            article.name
            == "Google's Bold Move: How The Tech Giant Used Generative AI To Revise Its Product Roadmap And Do It Safely"
        )
        assert (
            article.description
            == "Goodson dives in as explores how Google responded to ChatGPT by using foundation models and generative AI to create innovative products and improve its existing offerings."
        )
        assert article.date_published == "2023-04-07T14:40:00.0000000Z"
        assert (
            article.url
            == "https://www.forbes.com/sites/moorinsights/2023/04/07/googles-bold-move-how-the-tech-giant-used-generative-ai-to-revise-its-product-roadmap-and-do-it-safely/"
        )
        assert article.category == "ScienceAndTechnology"
