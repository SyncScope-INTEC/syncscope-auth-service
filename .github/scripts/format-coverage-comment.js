const core = require('@actions/core');
const github = require('@actions/github');

/**
 * Formats coverage data into a proper markdown table
 */
function formatCoverageTable(coverageData) {
    const lines = coverageData.split('\n').filter(line => line.trim());

    // Find the start of the coverage data (after the header)
    let dataStartIndex = -1;
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes('Name') && lines[i].includes('Stmts') && lines[i].includes('Miss') && lines[i].includes('Cover')) {
            dataStartIndex = i + 2; // Skip header and separator line
            break;
        }
    }

    if (dataStartIndex === -1) {
        return '| File | Coverage | Status |\n|------|----------|--------|\n| No coverage data available | N/A | ℹ️ |';
    }

    let table = '| File | Statements | Missing | Coverage | Status |\n';
    table += '|------|------------|---------|----------|--------|\n';

    // Process each file line
    for (let i = dataStartIndex; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line || line.startsWith('TOTAL')) continue;

        // Parse the line (format: filename statements missing coverage missing_lines)
        const parts = line.split(/\s+/);
        if (parts.length >= 4) {
            const filename = parts[0];
            const statements = parts[1];
            const missing = parts[2];
            const coverage = parts[3];

            // Determine status based on coverage percentage
            const coverageNum = parseInt(coverage.replace('%', ''));
            let status = '✅ Excellent';
            if (coverageNum < 50) {
                status = '❌ Needs Work';
            } else if (coverageNum < 70) {
                status = '⚠️ Below Average';
            } else if (coverageNum < 80) {
                status = '🟡 Good';
            } else if (coverageNum < 90) {
                status = '✅ Very Good';
            }

            // Clean up filename (remove path prefix if too long)
            const displayName = filename.length > 50 ? '...' + filename.slice(-47) : filename;

            table += `| \`${displayName}\` | ${statements} | ${missing} | **${coverage}** | ${status} |\n`;
        }
    }

    return table;
}

/**
 * Extracts differential coverage percentage from diff-cover output
 */
function extractDiffCoverage(diffCoverOutput) {
    const lines = diffCoverOutput.split('\n');
    for (const line of lines) {
        const match = line.match(/Diff Coverage: (\d+)%/);
        if (match) {
            return match[1] + '%';
        }
    }
    return 'N/A';
}

/**
 * Creates a properly formatted coverage comment
 */
function createCoverageComment(options) {
    const {
        coverage,
        status,
        changedFiles,
        isChanged,
        coverageReport,
        diffCoverOutput
    } = options;

    const emoji = status === 'passed' ? '✅' : '❌';
    const statusText = status === 'passed' ? 'PASSED' : 'FAILED';

    let comment = `## ${emoji} Differential Coverage Report - ${statusText}\n\n`;

    if (isChanged && changedFiles) {
        const diffCoveragePercent = extractDiffCoverage(diffCoverOutput);

        comment += `### 📊 Coverage Summary\n`;
        comment += `- **Overall Project Coverage:** ${coverage}%\n`;
        comment += `- **Differential Coverage:** ${diffCoveragePercent}\n`;
        comment += `- **Coverage Threshold:** 80% for modified files\n`;
        comment += `- **Modified Files:** ${changedFiles.split(' ').length} files\n\n`;

        comment += `### 📝 Modified Files Coverage\n\n`;

        // Format the coverage table properly
        const formattedTable = formatCoverageTable(coverageReport);
        comment += formattedTable + '\n\n';

        comment += `### 📈 Result\n`;
        if (status === 'passed') {
            comment += `✅ **All modified files meet the 80% coverage requirement!**\n\n`;
        } else {
            comment += `❌ **Some modified files are below the 80% coverage requirement**\n\n`;
        }

        comment += `<details>\n<summary>📋 View Full Coverage Report</summary>\n\n`;
        comment += `\`\`\`\n${coverageReport}\n\`\`\`\n</details>\n\n`;

        if (status === 'failed') {
            comment += `### 💡 How to Improve Coverage\n`;
            comment += `- Add unit tests for new functions and methods\n`;
            comment += `- Test edge cases and error conditions\n`;
            comment += `- Ensure all code paths are tested\n`;
            comment += `- Consider adding integration tests\n`;
        } else {
            comment += `### 🎉 Great job maintaining excellent test coverage!`;
        }

    } else {
        comment += `### 📊 Coverage Summary\n`;
        comment += `- **Overall Project Coverage:** ${coverage}%\n`;
        comment += `- **Modified Files:** None (non-Python changes only)\n\n`;
        comment += `✅ **No coverage check required** - This PR contains only documentation, configuration, or other non-code changes.\n\n`;
        comment += `<details>\n<summary>📋 View Full Coverage Report</summary>\n\n`;
        comment += `\`\`\`\n${coverageReport}\n\`\`\`\n</details>`;
    }

    return comment;
}

module.exports = {
    formatCoverageTable,
    extractDiffCoverage,
    createCoverageComment
};

// If running as standalone script
if (require.main === module) {
    const coverage = process.env.INPUT_COVERAGE || '0';
    const status = process.env.INPUT_STATUS || 'failed';
    const changedFiles = process.env.INPUT_CHANGED_FILES || '';
    const isChanged = process.env.INPUT_IS_CHANGED === 'true';
    const coverageReport = process.env.INPUT_COVERAGE_REPORT || '';
    const diffCoverOutput = process.env.INPUT_DIFF_COVER_OUTPUT || '';

    const comment = createCoverageComment({
        coverage,
        status,
        changedFiles,
        isChanged,
        coverageReport,
        diffCoverOutput
    });

    console.log(comment);
}
