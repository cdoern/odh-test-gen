// SCORER CALIBRATION: LOW QUALITY test (should score 2/10 - Rework)
//
// Issues demonstrated (compare with good-cypress-test.cy.ts for correct version):
// ❌ Coverage: 1/2 - Missing some TC requirements, has TODOs for specified items
// ❌ Assertions: 0/2 - Generic assertions, uses .should('exist') without specific checks
// ❌ Conventions: 1/2 - Uses brittle CSS selectors instead of data-testid (see Tiger Team cypress-tests.md)
// ❌ Test Data: 0/2 - Uses placeholder "test-model" instead of exact ID from TC
// ❌ Code Quality: 0/2 - TODOs for things specified in TC, hardcoded cy.wait() delays
//
// For Tiger Team Cypress patterns, see:
// ~/Code/Red-Hat-Quality-Tiger-Team/.claude/rules/cypress-tests.md

describe('TC-E2E-001', () => {
  it('should show model', () => {
    cy.visit('/model-catalog');

    // Anti-pattern: hardcoded wait instead of intercept
    cy.wait(2000);

    // Anti-pattern: brittle CSS selector instead of data-testid
    cy.get('.search-input').type('test-model'); // Placeholder instead of exact TC ID
    cy.get('.btn-primary').click();

    // Anti-pattern: another hardcoded wait
    cy.wait(1000);

    // Generic assertions without specific checks from TC
    cy.get('.model-card').should('exist');
    cy.contains('test-model').should('be.visible');

    // TODO: Check tool-calling badge          // TC specifies this - shouldn't be TODO!
    // TODO: Verify required CLI args          // TC specifies this - shouldn't be TODO!
    // TODO: Check chat template path          // TC specifies this - shouldn't be TODO!
  });
});
