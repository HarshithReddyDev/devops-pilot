data "aws_route53_zone" "this" {
  count        = var.create_dns_resources ? 1 : 0
  name         = var.root_domain
  private_zone = false
}

# --- ACM Certificate ---

resource "aws_acm_certificate" "this" {
  count = var.create_dns_resources ? 1 : 0

  domain_name       = local.customer_domain
  validation_method = "DNS"

  subject_alternative_names = ["*.${var.root_domain}"]

  lifecycle {
    create_before_destroy = true
  }

  tags = local.common_tags
}

resource "aws_route53_record" "cert_validation" {
  count = var.create_dns_resources ? length(aws_acm_certificate.this[0].domain_validation_options) : 0

  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = aws_acm_certificate.this[0].domain_validation_options[count.index].resource_record_name
  type    = aws_acm_certificate.this[0].domain_validation_options[count.index].resource_record_type
  records = [aws_acm_certificate.this[0].domain_validation_options[count.index].resource_record_value]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "this" {
  count = var.create_dns_resources ? 1 : 0

  certificate_arn         = aws_acm_certificate.this[0].arn
  validation_record_fqdns = aws_route53_record.cert_validation[*].fqdn
}

# --- Route53 ALIAS A Record ---

resource "aws_route53_record" "this" {
  count = var.create_dns_resources ? 1 : 0

  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = local.customer_domain
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}
