#!/bin/bash
# Investment Skills Setup Script
# Sets up Python venv + yfinance + verifies yfmcp MCP installation
# Usage: bash setup.sh
# Run from inside ~/.claude/skills/ directory or after cloning the repo

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  Claude Investment Skills - Setup Script"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

OK="${GREEN}✓${NC}"
WARN="${YELLOW}⚠${NC}"
FAIL="${RED}✗${NC}"

# ─────────────────────────────────────────────────────────────
# Step 1: Check Python 3
# ─────────────────────────────────────────────────────────────
echo "Step 1: Checking Python 3..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "  ${OK} Found: $PYTHON_VERSION"
else
    echo -e "  ${FAIL} Python 3 not found!"
    echo "      Install from https://www.python.org/downloads/"
    echo "      Or: brew install python3 (macOS)"
    exit 1
fi
echo ""

# ─────────────────────────────────────────────────────────────
# Step 2: Create venv at /tmp/.insider_venv
# ─────────────────────────────────────────────────────────────
echo "Step 2: Setting up Python venv at /tmp/.insider_venv..."
VENV_PATH="/tmp/.insider_venv"

if [ -d "$VENV_PATH" ]; then
    echo -e "  ${WARN} Existing venv found, removing..."
    rm -rf "$VENV_PATH"
fi

# Use system Python explicitly to avoid Homebrew Python issues with yfinance
SYSTEM_PYTHON="/Library/Developer/CommandLineTools/usr/bin/python3"
if [ ! -f "$SYSTEM_PYTHON" ]; then
    echo -e "  ${WARN} CommandLineTools Python not found, using default python3"
    SYSTEM_PYTHON="python3"
fi

$SYSTEM_PYTHON -m venv "$VENV_PATH"
echo -e "  ${OK} Created venv at $VENV_PATH"
echo ""

# ─────────────────────────────────────────────────────────────
# Step 3: Install yfinance and dependencies
# ─────────────────────────────────────────────────────────────
echo "Step 3: Installing Python packages (yfinance, pandas, numpy)..."
$VENV_PATH/bin/pip install --quiet --upgrade pip
$VENV_PATH/bin/pip install --quiet yfinance pandas numpy

echo -e "  ${OK} Installed yfinance"
echo ""

# ─────────────────────────────────────────────────────────────
# Step 4: Verify scripts work
# ─────────────────────────────────────────────────────────────
echo "Step 4: Verifying scripts..."

SCRIPTS_DIR="$HOME/.claude/skills/review-investment-screenshot/scripts"

if [ ! -d "$SCRIPTS_DIR" ]; then
    echo -e "  ${FAIL} Scripts directory not found: $SCRIPTS_DIR"
    echo "      Make sure review-investment-screenshot skill is installed."
    exit 1
fi

for script in insider_ratio.py cluster_buy_scan.py quote_pull.py option_walls.py max_pain.py; do
    if [ -f "$SCRIPTS_DIR/$script" ]; then
        chmod +x "$SCRIPTS_DIR/$script"
        echo -e "  ${OK} Found and made executable: $script"
    else
        echo -e "  ${WARN} Missing: $script"
    fi
done
echo ""

# ─────────────────────────────────────────────────────────────
# Step 5: Test insider_ratio.py (v3, openinsider primary)
# ─────────────────────────────────────────────────────────────
echo "Step 5a: Testing insider_ratio.py v3 with NVDA (--window 90)..."
TEST_OUTPUT=$($VENV_PATH/bin/python "$SCRIPTS_DIR/insider_ratio.py" NVDA --window 90 2>&1 | head -20 || true)

if echo "$TEST_OUTPUT" | grep -q "om_buy_count"; then
    echo -e "  ${OK} insider_ratio.py v3 works"
else
    echo -e "  ${WARN} insider_ratio.py output unclear. Try manually:"
    echo "      $VENV_PATH/bin/python $SCRIPTS_DIR/insider_ratio.py NVDA --window 90"
fi

echo "Step 5b: Testing cluster_buy_scan.py (openinsider scrape)..."
TEST_OUTPUT2=$($VENV_PATH/bin/python "$SCRIPTS_DIR/cluster_buy_scan.py" --days 30 --min-value 500000 --min-insiders 3 2>&1 | head -10 || true)

if echo "$TEST_OUTPUT2" | grep -q "n_clusters"; then
    echo -e "  ${OK} cluster_buy_scan.py works"
else
    echo -e "  ${WARN} cluster_buy_scan.py output unclear. Try manually:"
    echo "      $VENV_PATH/bin/python $SCRIPTS_DIR/cluster_buy_scan.py --days 30"
fi
echo ""

# ─────────────────────────────────────────────────────────────
# Step 6: Check yfmcp MCP installation
# ─────────────────────────────────────────────────────────────
echo "Step 6: Checking yfmcp MCP server..."
if command -v claude &> /dev/null; then
    MCP_LIST=$(claude mcp list 2>&1 || true)
    if echo "$MCP_LIST" | grep -q "yfmcp\|yfinance"; then
        echo -e "  ${OK} yfmcp MCP server already installed"
    else
        echo -e "  ${WARN} yfmcp not detected. To install:"
        echo "      claude mcp add yfmcp -- npx -y @modelcontextprotocol/yfmcp"
        echo "      (Or follow yfmcp installation docs)"
    fi
else
    echo -e "  ${WARN} 'claude' CLI not found in PATH"
    echo "      Install from: https://docs.claude.com/claude-code/install"
fi
echo ""

# ─────────────────────────────────────────────────────────────
# Step 7: Verify all skill folders exist
# ─────────────────────────────────────────────────────────────
echo "Step 7: Verifying skill installation..."
SKILLS_DIR="$HOME/.claude/skills"
REQUIRED_SKILLS=(
    "analyze-stock"
    "macro-risk-check"
    "earnings-prep"
    "leaps-screen"
    "option-wall-analysis"
    "find-untapped-thesis"
    "tax-optimize"
    "portfolio-audit"
    "narrative-reversal-screen"
    "sector-rotation-analysis"
    "review-investment-screenshot"
)

for skill in "${REQUIRED_SKILLS[@]}"; do
    if [ -f "$SKILLS_DIR/$skill/SKILL.md" ]; then
        echo -e "  ${OK} $skill"
    else
        echo -e "  ${WARN} Missing: $skill/SKILL.md"
    fi
done
echo ""

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════"
echo -e "  ${GREEN}Setup complete!${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Python venv: $VENV_PATH"
echo "Skills: $SKILLS_DIR"
echo ""
echo "Try in Claude Code:"
echo "  /analyze-stock NVDA"
echo "  /macro-risk-check"
echo "  /find-untapped-thesis 'AI Power'"
echo "  /portfolio-audit"
echo ""
echo "Read INVESTMENT-WORKFLOW.md for the full decision tree."
echo ""
echo "If yfmcp is missing, install it via:"
echo "  claude mcp add yfmcp -- npx -y @modelcontextprotocol/yfmcp"
echo "  (or check yfmcp docs for latest install command)"
echo ""
