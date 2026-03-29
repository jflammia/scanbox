"""Unit tests for OCR module with mocked system dependencies."""

import json
from unittest.mock import MagicMock, patch


class TestExtractTextByPage:
    @patch("scanbox.pipeline.ocr.pytesseract.image_to_string")
    @patch("scanbox.pipeline.ocr.convert_from_path")
    def test_extracts_text(self, mock_convert, mock_tesseract, tmp_path):
        from scanbox.pipeline.ocr import extract_text_by_page

        img1, img2 = MagicMock(), MagicMock()
        mock_convert.return_value = [img1, img2]
        mock_tesseract.side_effect = ["Page one text", "Page two text"]

        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        result = extract_text_by_page(pdf_path)

        assert result == {1: "Page one text", 2: "Page two text"}
        mock_convert.assert_called_once_with(str(pdf_path), dpi=300)

    @patch("scanbox.pipeline.ocr.pytesseract.image_to_string")
    @patch("scanbox.pipeline.ocr.convert_from_path")
    def test_single_page(self, mock_convert, mock_tesseract, tmp_path):
        from scanbox.pipeline.ocr import extract_text_by_page

        mock_convert.return_value = [MagicMock()]
        mock_tesseract.return_value = "Solo page"

        result = extract_text_by_page(tmp_path / "test.pdf")
        assert result == {1: "Solo page"}

    @patch("scanbox.pipeline.ocr.pytesseract.image_to_string")
    @patch("scanbox.pipeline.ocr.convert_from_path")
    def test_empty_pdf(self, mock_convert, mock_tesseract, tmp_path):
        from scanbox.pipeline.ocr import extract_text_by_page

        mock_convert.return_value = []
        result = extract_text_by_page(tmp_path / "test.pdf")
        assert result == {}


class TestRunOcr:
    @patch("scanbox.pipeline.ocr.extract_text_by_page")
    @patch("scanbox.pipeline.ocr.subprocess.run")
    def test_run_ocr_calls_ocrmypdf(self, mock_subprocess, mock_extract, tmp_path):
        from scanbox.pipeline.ocr import run_ocr

        mock_extract.return_value = {1: "Hello world", 2: "Second page"}

        input_path = tmp_path / "input.pdf"
        output_path = tmp_path / "output.pdf"
        text_json = tmp_path / "text.json"
        input_path.touch()

        run_ocr(input_path, output_path, text_json)

        # Verify ocrmypdf was called with correct args
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "ocrmypdf"
        assert "--deskew" in call_args
        assert "--skip-text" in call_args
        assert str(input_path) in call_args
        assert str(output_path) in call_args

        # Verify text JSON was written
        assert text_json.exists()
        text_data = json.loads(text_json.read_text())
        assert text_data["1"] == "Hello world"

    @patch("scanbox.pipeline.ocr.extract_text_by_page")
    @patch("scanbox.pipeline.ocr.subprocess.run")
    def test_run_ocr_custom_language(self, mock_subprocess, mock_extract, tmp_path):
        from scanbox.pipeline.ocr import run_ocr

        mock_extract.return_value = {}

        run_ocr(
            tmp_path / "in.pdf",
            tmp_path / "out.pdf",
            tmp_path / "text.json",
            language="deu",
        )

        call_args = mock_subprocess.call_args[0][0]
        lang_idx = call_args.index("--language")
        assert call_args[lang_idx + 1] == "deu"
