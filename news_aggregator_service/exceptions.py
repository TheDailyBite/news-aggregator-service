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


class PreviewUserNotExistsException(Exception):
    """Exception raised when a preview user does not exist."""

    def __init__(self, message: str = ""):
        if not message:
            self.message = f"Preview user does not exist."
        else:
            self.message = message
        super().__init__(self.message)
