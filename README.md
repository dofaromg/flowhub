# Organization Repository / 組織倉庫

## English

### What is this repository?

This is the `.github` organization repository for `dofaromg`. It provides default community health files, security workflows, and organizational resources that are automatically applied across all repositories in this organization.

### Available Resources and Deployment Capabilities

#### 🔒 Security Scanning
- **GitHub Actions Security Scanning**: Automated security scans for all workflow files using Semgrep
- **Workflow File**: `.github/workflows/action_scanning.yml`
- **Semgrep Rules**: Custom security rules for GitHub Actions in `semgrep-rules/actions/`

#### 📋 Community Health Files
- **Code of Conduct**: Based on Google's Open Source Community Guidelines
- **Contributing Guidelines**: Instructions for contributors including CLA requirements
- **Security Policy**: Vulnerability reporting process via https://g.co/vulnz

#### 🚀 Deployment and Access Spaces

This repository provides the following organizational capabilities:

1. **Automated Security Scanning**: All repositories in the organization automatically inherit security scanning workflows
2. **Standardized Community Guidelines**: Consistent code of conduct and contributing guidelines across all projects
3. **Security Vulnerability Management**: Centralized security reporting and handling process

#### How to Use These Resources

- **For Repository Owners**: These files automatically apply to repositories without their own versions
- **For Contributors**: Follow the guidelines in `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`
- **For Security**: Report vulnerabilities using the process outlined in `SECURITY.md`

---

## 中文

### 這個倉庫是什麼？

這是 `dofaromg` 組織的 `.github` 倉庫。它提供預設的社群健康文件、安全工作流程和組織資源，這些資源會自動應用到組織內的所有倉庫。

### 可用資源和部署能力

#### 🔒 安全掃描
- **GitHub Actions 安全掃描**: 使用 Semgrep 對所有工作流程文件進行自動化安全掃描
- **工作流程文件**: `.github/workflows/action_scanning.yml`
- **Semgrep 規則**: 在 `semgrep-rules/actions/` 中為 GitHub Actions 定制的安全規則

#### 📋 社群健康文件
- **行為準則**: 基於 Google 開源社群準則
- **貢獻指南**: 包括 CLA 要求在內的貢獻者說明
- **安全政策**: 通過 https://g.co/vulnz 的漏洞報告流程

#### 🚀 部署和存取空間

這個倉庫提供以下組織能力：

1. **自動化安全掃描**: 組織內的所有倉庫都會自動繼承安全掃描工作流程
2. **標準化社群準則**: 在所有專案中保持一致的行為準則和貢獻指南
3. **安全漏洞管理**: 集中式的安全報告和處理流程

#### 如何使用這些資源

- **對於倉庫擁有者**: 這些文件會自動應用到沒有自己版本的倉庫
- **對於貢獻者**: 遵循 `CONTRIBUTING.md` 和 `CODE_OF_CONDUCT.md` 中的指南
- **對於安全**: 使用 `SECURITY.md` 中概述的流程報告漏洞

## Repository Structure / 倉庫結構

```
├── .github/
│   └── workflows/
│       └── action_scanning.yml    # Security scanning workflow
├── semgrep-rules/
│   └── actions/
│       └── pull_request_target_needs_exception.yml  # Security rules
├── CODE_OF_CONDUCT.md             # Community guidelines
├── CONTRIBUTING.md                # Contribution guidelines
├── SECURITY.md                    # Security policy
└── README.md                      # This file
```

## Getting Started / 開始使用

1. **Repository Creators**: New repositories automatically inherit these defaults
2. **Contributors**: Read `CONTRIBUTING.md` before making contributions
3. **Security Researchers**: Follow the process in `SECURITY.md` for reporting vulnerabilities
4. **Developers**: The security workflows will automatically scan your GitHub Actions

---

*This repository serves as the organizational hub for community standards and automated security processes.*