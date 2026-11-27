import { Check } from 'lucide-react'

const steps = ['Automation details', 'Social account', 'Reel or Post URL', 'Review']

export function AutomationWizardSteps({ currentStep }: { currentStep: number }) {
  return <ol className="automation-wizard-steps" aria-label="Automation setup progress">
    {steps.map((label, index) => {
      const step = index + 1
      const state = currentStep === step ? 'current' : currentStep > step ? 'complete' : ''
      return <li className={state} key={label} aria-current={currentStep === step ? 'step' : undefined}>
        <span className="automation-step-number">{currentStep > step ? <Check size={14} /> : `0${step}`}</span>
        <span>{label}</span>
      </li>
    })}
  </ol>
}
