class ArticleSummarizationFailure(Exception):
    """Exception raised when an article summarization fails."""

    def __init__(self, article_id: str, message: str = ""):
        if not message:
            self.message = f"Article {article_id} summarization failed."
        else:
            self.message = message
        super().__init__(self.message)

    def __str__(self):
        return self.message


class UnsupportedCategoryException(Exception):
    """Exception raised when a requested category is not supported by the aggregator."""

    def __init__(self, message: str = ""):
        if not message:
            self.message = f"Unsupported category by aggregator."
        else:
            self.message = message
        super().__init__(self.message)
