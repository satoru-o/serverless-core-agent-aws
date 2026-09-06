# core/main.tf
resource "aws_s3_bucket" "rehab" {
  bucket = "sca-aws-rehab-bucket"  # グローバル一意。重複したら適当な文字列を足す

  tags = {
    Purpose = "terraform-rehab"
  }
}

resource "aws_s3_bucket_versioning" "rehab" {
  bucket = aws_s3_bucket.rehab.id
  versioning_configuration {
    status = "Suspended"  # リハビリ用なので不要
  }
}