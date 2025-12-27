# ref: https://registry.terraform.io/providers/keycloak/keycloak/5.0.0/docs/resources/openid_client

variable "default_password" {
  type = string
}

variable "login_theme" {
  type    = string
  default = "keycloak"
}

variable "account_theme" {
  type    = string
  default = "keycloak.v2"
}

variable "admin_theme" {
  type    = string
  default = "keycloak.v2"
}

variable "email_theme" {
  type    = string
  default = "keycloak"
}

variable "root_url" {
  type    = string
  default = "http://localhost:5173"
}

variable "valid_redirect_uris" {
  type    = list(string)
  default = ["*"]
}

variable "valid_post_logout_redirect_uris" {
  type    = list(string)
  default = ["+"]
}

variable "web_origins" {
  type    = list(string)
  default = ["*"]
}

data "keycloak_realm" "master" {
  realm = "master"
}

# ============================================================================
# Purchasing Realm (for purchasing agents)
# ============================================================================

resource "keycloak_realm" "purchasing" {
  realm             = "purchasing"
  enabled           = true
  display_name      = "Purchasing Organization"
  display_name_html = "<b>Purchasing Organization</b>"

  login_theme = var.login_theme
  access_code_lifespan = "30m"
  ssl_required    = "none"
  password_policy = "upperCase(1) and length(8) and notUsername(undefined)"

  internationalization {
    supported_locales = ["en", "de", "es"]
    default_locale = "en"
  }

  security_defenses {
    headers {
      x_frame_options                     = "SAMEORIGIN"
      content_security_policy             = "frame-src 'self'; frame-ancestors 'self'; object-src 'none';"
      content_security_policy_report_only = ""
      x_content_type_options              = "nosniff"
      x_robots_tag                        = "none"
      x_xss_protection                    = "1; mode=block"
      strict_transport_security           = "max-age=31536000; includeSubDomains"
    }
    brute_force_detection {
      permanent_lockout                = false
      max_login_failures               = 30
      wait_increment_seconds           = 60
      quick_login_check_milli_seconds  = 1000
      minimum_quick_login_wait_seconds = 60
      max_failure_wait_seconds         = 900
      failure_reset_time_seconds       = 43200
    }
  }
}

# User Profile configuration to allow custom attributes (required for Keycloak 26+)
resource "keycloak_realm_user_profile" "purchasing_user_profile" {
  realm_id = keycloak_realm.purchasing.id

  attribute {
    name         = "username"
    display_name = "$${username}"

    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }

    validator {
      name = "length"
      config = {
        min = "3"
        max = "255"
      }
    }
    validator {
      name = "username-prohibited-characters"
    }
    validator {
      name = "up-username-not-idn-homograph"
    }
  }

  attribute {
    name         = "email"
    display_name = "$${email}"

    required_for_roles = ["user"]

    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }

    validator {
      name = "email"
    }
    validator {
      name = "length"
      config = {
        max = "255"
      }
    }
  }

  attribute {
    name         = "firstName"
    display_name = "$${firstName}"

    required_for_roles = ["user"]

    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }

    validator {
      name = "length"
      config = {
        max = "255"
      }
    }
    validator {
      name = "person-name-prohibited-characters"
    }
  }

  attribute {
    name         = "lastName"
    display_name = "$${lastName}"

    required_for_roles = ["user"]

    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }

    validator {
      name = "length"
      config = {
        max = "255"
      }
    }
    validator {
      name = "person-name-prohibited-characters"
    }
  }

  # Custom attribute for organization (multi-valued)
  attribute {
    name         = "organization"
    display_name = "Organization"
    multi_valued  = true

    permissions {
      view = ["admin", "user"]
      edit = ["admin"]
    }
  }

  # Custom attribute for department (multi-valued)
  attribute {
    name         = "department"
    display_name = "Department"
    multi_valued  = true

    permissions {
      view = ["admin", "user"]
      edit = ["admin"]
    }
  }

  group {
    name                = "user-metadata"
    display_header      = "User metadata"
    display_description = "Attributes, which refer to user metadata"
  }
}

resource "keycloak_openid_client" "purchasing_client" {
  realm_id                        = keycloak_realm.purchasing.id
  client_id                       = "purchasing"
  access_type                     = "PUBLIC"
  direct_access_grants_enabled    = true
  standard_flow_enabled           = true
  valid_redirect_uris             = var.valid_redirect_uris
  valid_post_logout_redirect_uris = var.valid_post_logout_redirect_uris
  web_origins                     = var.web_origins
  root_url                        = var.root_url
}

# Protocol mapper for organization claim (purchasing)
resource "keycloak_openid_user_attribute_protocol_mapper" "purchasing_organization_mapper" {
  realm_id  = keycloak_realm.purchasing.id
  client_id = keycloak_openid_client.purchasing_client.id
  name      = "organization-mapper"

  user_attribute   = "organization"
  claim_name       = "organization"
  claim_value_type = "String"
  multivalued      = true

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

# Protocol mapper for department claim (purchasing)
resource "keycloak_openid_user_attribute_protocol_mapper" "purchasing_department_mapper" {
  realm_id  = keycloak_realm.purchasing.id
  client_id = keycloak_openid_client.purchasing_client.id
  name      = "department-mapper"

  user_attribute   = "department"
  claim_name       = "department"
  claim_value_type = "String"
  multivalued      = true

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

# Purchasing agent user
resource "keycloak_user" "purchasing_agent" {
  realm_id   = keycloak_realm.purchasing.id
  username   = "purchasing_agent"
  email      = "purchasing_agent@acme-corp.com"
  first_name = "Purchasing"
  last_name  = "Agent"
  enabled    = true

  attributes = {
    "organization" = "Acme Corp"
    "department"   = "Procurement"
  }

  initial_password {
    value     = var.default_password
    temporary = false
  }

  # User profile must be configured before creating users with custom attributes
  depends_on = [keycloak_realm_user_profile.purchasing_user_profile]
}

# Approver user for high-value purchase order approvals
resource "keycloak_user" "approver" {
  realm_id   = keycloak_realm.purchasing.id
  username   = "approver"
  email      = "approver@acme-corp.com"
  first_name = "Alice"
  last_name  = "Approver"
  enabled    = true

  attributes = {
    "organization" = "Acme Corp"
    "department"   = "Finance"
  }

  initial_password {
    value     = var.default_password
    temporary = false
  }

  # User profile must be configured before creating users with custom attributes
  depends_on = [keycloak_realm_user_profile.purchasing_user_profile]
}

# ============================================================================
# Supplier Realm (for supplier agents)
# ============================================================================

resource "keycloak_realm" "supplier" {
  realm             = "supplier"
  enabled           = true
  display_name      = "Supplier Organization"
  display_name_html = "<b>Supplier Organization</b>"

  login_theme = var.login_theme
  access_code_lifespan = "30m"
  ssl_required    = "none"
  password_policy = "upperCase(1) and length(8) and notUsername(undefined)"

  internationalization {
    supported_locales = ["en", "de", "es"]
    default_locale = "en"
  }

  security_defenses {
    headers {
      x_frame_options                     = "SAMEORIGIN"
      content_security_policy             = "frame-src 'self'; frame-ancestors 'self'; object-src 'none';"
      content_security_policy_report_only = ""
      x_content_type_options              = "nosniff"
      x_robots_tag                        = "none"
      x_xss_protection                    = "1; mode=block"
      strict_transport_security           = "max-age=31536000; includeSubDomains"
    }
    brute_force_detection {
      permanent_lockout                = false
      max_login_failures               = 30
      wait_increment_seconds           = 60
      quick_login_check_milli_seconds  = 1000
      minimum_quick_login_wait_seconds = 60
      max_failure_wait_seconds         = 900
      failure_reset_time_seconds       = 43200
    }
  }
}

# User Profile configuration to allow custom attributes (required for Keycloak 26+)
resource "keycloak_realm_user_profile" "supplier_user_profile" {
  realm_id = keycloak_realm.supplier.id

  attribute {
    name         = "username"
    display_name = "$${username}"

    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }

    validator {
      name = "length"
      config = {
        min = "3"
        max = "255"
      }
    }
    validator {
      name = "username-prohibited-characters"
    }
    validator {
      name = "up-username-not-idn-homograph"
    }
  }

  attribute {
    name         = "email"
    display_name = "$${email}"

    required_for_roles = ["user"]

    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }

    validator {
      name = "email"
    }
    validator {
      name = "length"
      config = {
        max = "255"
      }
    }
  }

  attribute {
    name         = "firstName"
    display_name = "$${firstName}"

    required_for_roles = ["user"]

    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }

    validator {
      name = "length"
      config = {
        max = "255"
      }
    }
    validator {
      name = "person-name-prohibited-characters"
    }
  }

  attribute {
    name         = "lastName"
    display_name = "$${lastName}"

    required_for_roles = ["user"]

    permissions {
      view = ["admin", "user"]
      edit = ["admin", "user"]
    }

    validator {
      name = "length"
      config = {
        max = "255"
      }
    }
    validator {
      name = "person-name-prohibited-characters"
    }
  }

  # Custom attribute for organization (multi-valued)
  attribute {
    name         = "organization"
    display_name = "Organization"
    multi_valued  = true

    permissions {
      view = ["admin", "user"]
      edit = ["admin"]
    }
  }

  # Custom attribute for department (multi-valued)
  attribute {
    name         = "department"
    display_name = "Department"
    multi_valued  = true

    permissions {
      view = ["admin", "user"]
      edit = ["admin"]
    }
  }

  group {
    name                = "user-metadata"
    display_header      = "User metadata"
    display_description = "Attributes, which refer to user metadata"
  }
}

resource "keycloak_openid_client" "supplier_client" {
  realm_id                        = keycloak_realm.supplier.id
  client_id                       = "supplier"
  access_type                     = "PUBLIC"
  direct_access_grants_enabled    = true
  standard_flow_enabled           = true
  valid_redirect_uris             = var.valid_redirect_uris
  valid_post_logout_redirect_uris = var.valid_post_logout_redirect_uris
  web_origins                     = var.web_origins
  root_url                        = var.root_url
}

# Protocol mapper for organization claim (supplier)
resource "keycloak_openid_user_attribute_protocol_mapper" "supplier_organization_mapper" {
  realm_id  = keycloak_realm.supplier.id
  client_id = keycloak_openid_client.supplier_client.id
  name      = "organization-mapper"

  user_attribute   = "organization"
  claim_name       = "organization"
  claim_value_type = "String"
  multivalued      = true

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

# Protocol mapper for department claim (supplier)
resource "keycloak_openid_user_attribute_protocol_mapper" "supplier_department_mapper" {
  realm_id  = keycloak_realm.supplier.id
  client_id = keycloak_openid_client.supplier_client.id
  name      = "department-mapper"

  user_attribute   = "department"
  claim_name       = "department"
  claim_value_type = "String"
  multivalued      = true

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

# Supplier agent user
resource "keycloak_user" "supplier_agent" {
  realm_id   = keycloak_realm.supplier.id
  username   = "supplier_agent"
  email      = "supplier_agent@supplier-inc.com"
  first_name = "Supplier"
  last_name  = "Agent"
  enabled    = true

  attributes = {
    "organization" = "Supplier Inc"
    "department"   = "Sales"
  }

  initial_password {
    value     = var.default_password
    temporary = false
  }

  # User profile must be configured before creating users with custom attributes
  depends_on = [keycloak_realm_user_profile.supplier_user_profile]
}
