#!/bin/bash

# Script to update project from template upstream
# Usage: ./update_template.sh

# Prevent Git from opening an editor for commit messages
export GIT_MERGE_AUTOEDIT=no

TEMPLATE_REPO="https://github.com/LuighiV/iic-osic-tools-project-template.git"
TEMPLATE_BRANCH="main"

# Function to prompt user for confirmation
prompt_user() {
    while true; do
        read -p "$1 (y/n): " yn
        case $yn in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Please answer yes (y) or no (n).";;
        esac
    done
}

# Function to handle merge conflicts automatically
resolve_conflicts_automatically() {
    echo ""
    echo "🔧 Merge conflicts detected. Here are your options:"
    echo "1) Accept template version (recommended for most users)"
    echo "2) Accept your current version"
    echo "3) Abort update and resolve manually"
    echo ""
    
    while true; do
        read -p "Choose option (1/2/3): " choice
        case $choice in
            1)
                echo "✅ Accepting template version for all conflicts..."
                git checkout --theirs .
                git add .
                git commit -m "Merge template updates (accepted template version)"
                return 0
                ;;
            2)
                echo "✅ Keeping your current version for all conflicts..."
                git checkout --ours .
                git add .
                git commit -m "Merge template updates (kept local version)"
                return 0
                ;;
            3)
                echo "❌ Aborting update. Run 'git merge --abort' to cancel the merge."
                git merge --abort
                return 1
                ;;
            *)
                echo "Please choose 1, 2, or 3."
                ;;
        esac
    done
}

# Check if we're inside a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "❌ This is not a git repository. Please run this script from inside your project folder."
  exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  You have uncommitted changes in your repository."
    echo "   It's recommended to commit or stash your changes before updating."
    if ! prompt_user "Do you want to continue anyway?"; then
        echo "❌ Update cancelled. Please commit your changes first."
        exit 1
    fi
fi

# Show what this script will do
echo "🔄 Template Update Script"
echo "========================"
echo "This script will:"
echo "• Fetch the latest changes from the template repository"
echo "• Attempt to merge them into your current branch"
echo "• Help resolve any conflicts that arise"
echo ""
echo "Template repository: $TEMPLATE_REPO"
echo "Template branch: $TEMPLATE_BRANCH"
echo ""

if ! prompt_user "Do you want to proceed with the update?"; then
    echo "❌ Update cancelled by user."
    exit 0
fi

# Check if 'upstream' remote already exists
if git remote get-url upstream > /dev/null 2>&1; then
  echo "🔄 Using existing 'upstream' remote."
else
  echo "➕ Adding upstream remote: $TEMPLATE_REPO"
  git remote add upstream "$TEMPLATE_REPO"
fi

# Fetch updates from upstream
echo "📥 Fetching updates from upstream..."
git fetch upstream

# Show what changes are available
echo ""
echo "📊 Checking for available updates..."
CHANGES=$(git log HEAD..upstream/$TEMPLATE_BRANCH --oneline --no-merges 2>/dev/null | wc -l)
if [ "$CHANGES" -eq 0 ]; then
    echo "✅ Your project is already up to date with the template!"
    exit 0
fi

echo "📝 Found $CHANGES new commits in the template."
echo ""
echo "Recent template changes:"
git log HEAD..upstream/$TEMPLATE_BRANCH --oneline --no-merges -5 2>/dev/null || echo "Unable to show changes"
echo ""

if ! prompt_user "Do you want to merge these changes?"; then
    echo "❌ Merge cancelled by user."
    exit 0
fi

# Merge changes from the upstream template
echo "🔀 Merging changes from upstream/$TEMPLATE_BRANCH into your current branch..."
if git merge upstream/"$TEMPLATE_BRANCH" --allow-unrelated-histories -m "Merge template updates from upstream"; then
    echo "✅ Update completed successfully! No conflicts to resolve."
    echo "🎉 Your project is now up to date with the template."
else
    echo ""
    echo "⚠️  Merge conflicts occurred during the update."
    resolve_conflicts_automatically
    if [ $? -eq 0 ]; then
        echo "✅ Update completed successfully!"
        echo "🎉 Your project is now up to date with the template."
    else
        echo "❌ Update was aborted."
        echo "💡 You can run this script again later, or manually resolve conflicts using:"
        echo "   git status          # See conflicted files"
        echo "   git merge --abort   # Cancel the merge"
        exit 1
    fi
fi

echo ""
echo "📋 Next steps:"
echo "• Review the changes: git log --oneline -10"
echo "• Test your project to ensure everything works"
echo "• Push changes to your remote repository: git push origin main"
