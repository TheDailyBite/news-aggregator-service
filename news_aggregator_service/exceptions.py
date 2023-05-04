class ArticleSummarizationFailure(Exception):
    """Exception raised when an article summarization fails."""

    def __init__(self, article_id: str):
        self.message = f"Article {article_id} summarization failed."
        super().__init__(self.message)

    def __str__(self):
        return self.message
