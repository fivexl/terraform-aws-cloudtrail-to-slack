DESCRIBE           := $(shell git fetch --all > /dev/null && git describe --match "v*" --always --tags)
DESCRIBE_PARTS     := $(subst -, ,$(DESCRIBE))
# 'v0.2.0'
VERSION_TAG        := $(word 1,$(DESCRIBE_PARTS))
# '0.2.0'
VERSION            := $(subst v,,$(VERSION_TAG))
# '0 2 0'
VERSION_PARTS      := $(subst ., ,$(VERSION))

MAJOR              := $(word 1,$(VERSION_PARTS))
MINOR              := $(word 2,$(VERSION_PARTS))
PATCH              := $(word 3,$(VERSION_PARTS))

BUMP ?= patch
ifeq ($(BUMP), major)
NEXT_VERSION		:= $(shell echo $$(($(MAJOR)+1)).0.0)
else ifeq ($(BUMP), minor)
NEXT_VERSION		:= $(shell echo $(MAJOR).$$(($(MINOR)+1)).0)
else
NEXT_VERSION		:= $(shell echo $(MAJOR).$(MINOR).$$(($(PATCH)+1)))
endif
NEXT_TAG 			:= v$(NEXT_VERSION)

all: fmt validate

init: ## Initialize a Terraform working directory
	@echo "+ $@"
	@terraform init -backend=false > /dev/null

.PHONY: fmt
fmt: ## Checks config files against canonical format
	@echo "+ $@"
	@terraform fmt -check=true -recursive

.PHONY: validate
validate: init ## Validates the Terraform files
	@echo "+ $@"
	@AWS_REGION=eu-west-1 terraform validate

documentation: ## Generates README.md from static snippets and Terraform variables
	terraform-docs markdown table . > docs/part2.md
	cat docs/*.md > README.md

bump ::
	@echo bumping version from $(VERSION_TAG) to $(NEXT_TAG)
	@sed -i '' s/$(VERSION)/$(NEXT_VERSION)/g docs/part1.md

.PHONY: check-git-clean
check-git-clean:
	@git diff-index --quiet HEAD || (echo "There are uncomitted changes"; exit 1)

.PHONY: check-git-branch
check-git-branch: check-git-clean
	git fetch origin --tags --prune
	git checkout master

release: check-git-branch bump documentation
	git add README.md docs/part1.md
	git commit -vsam "Bump version to $(NEXT_TAG)"
	git tag -a $(NEXT_TAG) -m "$(NEXT_TAG)"
	git push origin $(NEXT_TAG)
	git push
	# create GH release if GITHUB_TOKEN is set
	if [ ! -z "${GITHUB_TOKEN}" ] ; then 												\
    	curl 																		\
    		-H "Authorization: token ${GITHUB_TOKEN}" 								\
    		-X POST 																\
    		-H "Accept: application/vnd.github.v3+json"								\
    		https://api.github.com/repos/stroeer/terraform-aws-cloudtrail-to-slack/releases \
    		-d "{\"tag_name\":\"3.0.1\",\"generate_release_notes\":true}"; 									\
	fi;

help: ## Display this help screen
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'	
