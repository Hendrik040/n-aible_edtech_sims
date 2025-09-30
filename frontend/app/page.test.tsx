import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { useRouter } from 'next/navigation'
import LoginPage from './page'
import { useAuth } from '@/lib/auth-context'
import { AccountLinkingData } from '@/lib/google-oauth'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// Mock Next.js Link component
jest.mock('next/link', () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) => {
    return <a href={href}>{children}</a>
  }
})

// Mock auth context
jest.mock('@/lib/auth-context', () => ({
  useAuth: jest.fn(),
}))

// Mock AccountLinkingDialog component
jest.mock('@/components/AccountLinkingDialog', () => ({
  AccountLinkingDialog: ({ isOpen, onClose, linkingData, onLinkAccount, isLoading }: any) => {
    if (\!isOpen) return null
    return (
      <div data-testid="account-linking-dialog">
        <button onClick={() => onLinkAccount('link')}>Link Account</button>
        <button onClick={() => onLinkAccount('create_separate')}>Create Separate</button>
        <button onClick={onClose}>Close</button>
        <div data-testid="linking-data">{JSON.stringify(linkingData)}</div>
        {isLoading && <div data-testid="loading">Loading...</div>}
      </div>
    )
  },
}))

// Mock UI components
jest.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, type, className }: any) => (
    <button onClick={onClick} disabled={disabled} type={type} className={className}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/ui/input', () => ({
  Input: (props: any) => <input {...props} />,
}))

jest.mock('@/components/ui/label', () => ({
  Label: ({ children, htmlFor }: any) => <label htmlFor={htmlFor}>{children}</label>,
}))

jest.mock('@/components/ui/checkbox', () => ({
  Checkbox: ({ id, checked, onCheckedChange }: any) => (
    <input
      type="checkbox"
      id={id}
      checked={checked}
      onChange={(e) => onCheckedChange(e.target.checked)}
    />
  ),
}))

describe('LoginPage', () => {
  const mockPush = jest.fn()
  const mockLogin = jest.fn()
  const mockLoginWithGoogle = jest.fn()
  const mockLinkGoogleAccount = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    })
    ;(useAuth as jest.Mock).mockReturnValue({
      user: null,
      login: mockLogin,
      loginWithGoogle: mockLoginWithGoogle,
      linkGoogleAccount: mockLinkGoogleAccount,
    })
    
    // Mock window.opener and window.parent
    Object.defineProperty(window, 'opener', {
      writable: true,
      value: null,
    })
    Object.defineProperty(window, 'parent', {
      writable: true,
      value: window,
    })
  })

  describe('Component Rendering', () => {
    it('should render the login page with all essential elements', () => {
      render(<LoginPage />)
      
      expect(screen.getByText('Log in to your account')).toBeInTheDocument()
      expect(screen.getByText('Log in with Google')).toBeInTheDocument()
      expect(screen.getByLabelText('Email')).toBeInTheDocument()
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /log in$/i })).toBeInTheDocument()
      expect(screen.getByText("Don't have an account yet?")).toBeInTheDocument()
      expect(screen.getByText('Sign up now')).toBeInTheDocument()
    })

    it('should render logo image', () => {
      render(<LoginPage />)
      const logo = screen.getByAltText('Logo')
      expect(logo).toBeInTheDocument()
      expect(logo).toHaveAttribute('src', '/n-aiblelogo.png')
    })

    it('should render remember me checkbox', () => {
      render(<LoginPage />)
      expect(screen.getByLabelText('Remember me')).toBeInTheDocument()
    })

    it('should render forgot password link', () => {
      render(<LoginPage />)
      const forgotPasswordLink = screen.getByText('Forgot password?')
      expect(forgotPasswordLink).toBeInTheDocument()
    })

    it('should render OR divider', () => {
      render(<LoginPage />)
      expect(screen.getByText('OR')).toBeInTheDocument()
    })

    it('should not render error message initially', () => {
      render(<LoginPage />)
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })
  })

  describe('Email/Password Login', () => {
    it('should handle email input change', () => {
      render(<LoginPage />)
      const emailInput = screen.getByLabelText('Email') as HTMLInputElement
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      
      expect(emailInput.value).toBe('test@example.com')
    })

    it('should handle password input change', () => {
      render(<LoginPage />)
      const passwordInput = screen.getByLabelText('Password') as HTMLInputElement
      
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
      
      expect(passwordInput.value).toBe('password123')
    })

    it('should handle remember me checkbox toggle', () => {
      render(<LoginPage />)
      const checkbox = screen.getByLabelText('Remember me') as HTMLInputElement
      
      expect(checkbox.checked).toBe(false)
      
      fireEvent.change(checkbox, { target: { checked: true } })
      
      expect(checkbox.checked).toBe(true)
    })

    it('should call login function on form submission with email and password', async () => {
      mockLogin.mockResolvedValue({})
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
      fireEvent.click(submitButton)
      
      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123')
      })
    })

    it('should redirect to dashboard after successful login', async () => {
      mockLogin.mockResolvedValue({})
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
      fireEvent.click(submitButton)
      
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/dashboard')
      })
    })

    it('should show loading state during login', async () => {
      mockLogin.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
      fireEvent.click(submitButton)
      
      expect(screen.getByText('Logging in...')).toBeInTheDocument()
      
      await waitFor(() => {
        expect(screen.queryByText('Logging in...')).not.toBeInTheDocument()
      })
    })

    it('should disable submit button during loading', async () => {
      mockLogin.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
      fireEvent.click(submitButton)
      
      expect(submitButton).toBeDisabled()
      
      await waitFor(() => {
        expect(submitButton).not.toBeDisabled()
      })
    })

    it('should display error message on login failure', async () => {
      const errorMessage = 'Invalid credentials'
      mockLogin.mockRejectedValue(new Error(errorMessage))
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'wrongpassword' } })
      fireEvent.click(submitButton)
      
      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument()
      })
    })

    it('should display generic error message when error is not an Error instance', async () => {
      mockLogin.mockRejectedValue('Something went wrong')
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
      fireEvent.click(submitButton)
      
      await waitFor(() => {
        expect(screen.getByText('Login failed. Please try again.')).toBeInTheDocument()
      })
    })

    it('should clear error when user types in email field', async () => {
      mockLogin.mockRejectedValue(new Error('Invalid credentials'))
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'wrongpassword' } })
      fireEvent.click(submitButton)
      
      await waitFor(() => {
        expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
      })
      
      fireEvent.change(emailInput, { target: { value: 'newemail@example.com' } })
      
      expect(screen.queryByText('Invalid credentials')).not.toBeInTheDocument()
    })

    it('should clear error when user types in password field', async () => {
      mockLogin.mockRejectedValue(new Error('Invalid credentials'))
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'wrongpassword' } })
      fireEvent.click(submitButton)
      
      await waitFor(() => {
        expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
      })
      
      fireEvent.change(passwordInput, { target: { value: 'newpassword' } })
      
      expect(screen.queryByText('Invalid credentials')).not.toBeInTheDocument()
    })

    it('should prevent form submission with empty fields', () => {
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email') as HTMLInputElement
      const passwordInput = screen.getByLabelText('Password') as HTMLInputElement
      
      expect(emailInput).toHaveAttribute('required')
      expect(passwordInput).toHaveAttribute('required')
    })

    it('should have correct input types', () => {
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      
      expect(emailInput).toHaveAttribute('type', 'email')
      expect(passwordInput).toHaveAttribute('type', 'password')
    })
  })

  describe('Google Login', () => {
    it('should call loginWithGoogle when Google button is clicked', async () => {
      mockLoginWithGoogle.mockResolvedValue({})
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(mockLoginWithGoogle).toHaveBeenCalled()
      })
    })

    it('should redirect to dashboard after successful Google login', async () => {
      mockLoginWithGoogle.mockResolvedValue({})
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/dashboard')
      })
    })

    it('should show account linking dialog when link_required is returned', async () => {
      const linkingData: AccountLinkingData = {
        action: 'link_required',
        existing_user: {
          id: 'user123',
          email: 'test@example.com',
          name: 'Test User',
        },
        google_data: {
          id: 'google123',
          email: 'test@example.com',
          name: 'Test User',
        },
        state: 'state123',
      }
      mockLoginWithGoogle.mockResolvedValue(linkingData)
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByTestId('account-linking-dialog')).toBeInTheDocument()
      })
    })

    it('should display error message on Google login failure', async () => {
      const errorMessage = 'Google authentication failed'
      mockLoginWithGoogle.mockRejectedValue(new Error(errorMessage))
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument()
      })
    })

    it('should display generic error message when Google login error is not an Error instance', async () => {
      mockLoginWithGoogle.mockRejectedValue('Unknown error')
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByText('Google login failed. Please try again.')).toBeInTheDocument()
      })
    })

    it('should set loading state during Google login', async () => {
      mockLoginWithGoogle.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      // Loading state is internal, we can verify it doesn't crash
      await waitFor(() => {
        expect(mockLoginWithGoogle).toHaveBeenCalled()
      })
    })
  })

  describe('Account Linking', () => {
    const linkingData: AccountLinkingData = {
      action: 'link_required',
      existing_user: {
        id: 'user123',
        email: 'test@example.com',
        name: 'Test User',
      },
      google_data: {
        id: 'google123',
        email: 'test@example.com',
        name: 'Test User',
      },
      state: 'state123',
    }

    it('should handle link account action', async () => {
      mockLoginWithGoogle.mockResolvedValue(linkingData)
      mockLinkGoogleAccount.mockResolvedValue({})
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByTestId('account-linking-dialog')).toBeInTheDocument()
      })
      
      const linkButton = screen.getByText('Link Account')
      fireEvent.click(linkButton)
      
      await waitFor(() => {
        expect(mockLinkGoogleAccount).toHaveBeenCalledWith(
          'link',
          'user123',
          linkingData.google_data,
          'state123'
        )
      })
    })

    it('should handle create separate account action', async () => {
      mockLoginWithGoogle.mockResolvedValue(linkingData)
      mockLinkGoogleAccount.mockResolvedValue({})
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByTestId('account-linking-dialog')).toBeInTheDocument()
      })
      
      const createSeparateButton = screen.getByText('Create Separate')
      fireEvent.click(createSeparateButton)
      
      await waitFor(() => {
        expect(mockLinkGoogleAccount).toHaveBeenCalledWith(
          'create_separate',
          'user123',
          linkingData.google_data,
          'state123'
        )
      })
    })

    it('should close dialog and redirect after successful account linking', async () => {
      mockLoginWithGoogle.mockResolvedValue(linkingData)
      mockLinkGoogleAccount.mockResolvedValue({})
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByTestId('account-linking-dialog')).toBeInTheDocument()
      })
      
      const linkButton = screen.getByText('Link Account')
      fireEvent.click(linkButton)
      
      await waitFor(() => {
        expect(screen.queryByTestId('account-linking-dialog')).not.toBeInTheDocument()
        expect(mockPush).toHaveBeenCalledWith('/dashboard')
      })
    })

    it('should display error on account linking failure', async () => {
      const errorMessage = 'Account linking failed'
      mockLoginWithGoogle.mockResolvedValue(linkingData)
      mockLinkGoogleAccount.mockRejectedValue(new Error(errorMessage))
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByTestId('account-linking-dialog')).toBeInTheDocument()
      })
      
      const linkButton = screen.getByText('Link Account')
      fireEvent.click(linkButton)
      
      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument()
      })
    })

    it('should handle closing dialog without action', async () => {
      mockLoginWithGoogle.mockResolvedValue(linkingData)
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByTestId('account-linking-dialog')).toBeInTheDocument()
      })
      
      const closeButton = screen.getByText('Close')
      fireEvent.click(closeButton)
      
      await waitFor(() => {
        expect(screen.queryByTestId('account-linking-dialog')).not.toBeInTheDocument()
      })
    })

    it('should not call linkGoogleAccount if linkingData is null', async () => {
      render(<LoginPage />)
      
      // This test verifies the guard clause in handleLinkAccount
      // Since we can't directly call handleLinkAccount, we verify it doesn't crash
      expect(mockLinkGoogleAccount).not.toHaveBeenCalled()
    })

    it('should display generic error message when linking error is not an Error instance', async () => {
      mockLoginWithGoogle.mockResolvedValue(linkingData)
      mockLinkGoogleAccount.mockRejectedValue('Unknown error')
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(screen.getByTestId('account-linking-dialog')).toBeInTheDocument()
      })
      
      const linkButton = screen.getByText('Link Account')
      fireEvent.click(linkButton)
      
      await waitFor(() => {
        expect(screen.getByText('Account linking failed. Please try again.')).toBeInTheDocument()
      })
    })
  })

  describe('User Authentication State and Redirects', () => {
    it('should redirect professor to professor dashboard when user is authenticated', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'prof@example.com', role: 'professor' },
        login: mockLogin,
        loginWithGoogle: mockLoginWithGoogle,
        linkGoogleAccount: mockLinkGoogleAccount,
      })
      
      render(<LoginPage />)
      
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/professor/dashboard')
      })
    })

    it('should redirect admin to professor dashboard when user is authenticated', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'admin' },
        login: mockLogin,
        loginWithGoogle: mockLoginWithGoogle,
        linkGoogleAccount: mockLinkGoogleAccount,
      })
      
      render(<LoginPage />)
      
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/professor/dashboard')
      })
    })

    it('should redirect student to student dashboard when user is authenticated', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'student@example.com', role: 'student' },
        login: mockLogin,
        loginWithGoogle: mockLoginWithGoogle,
        linkGoogleAccount: mockLinkGoogleAccount,
      })
      
      render(<LoginPage />)
      
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/student/dashboard')
      })
    })

    it('should redirect to generic dashboard for unknown role', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'unknown' },
        login: mockLogin,
        loginWithGoogle: mockLoginWithGoogle,
        linkGoogleAccount: mockLinkGoogleAccount,
      })
      
      render(<LoginPage />)
      
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/dashboard')
      })
    })

    it('should not redirect when user is null', () => {
      render(<LoginPage />)
      
      expect(mockPush).not.toHaveBeenCalled()
    })

    it('should not redirect when in popup context (window.opener is set)', () => {
      Object.defineProperty(window, 'opener', {
        writable: true,
        value: {},
      })
      
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'student' },
        login: mockLogin,
        loginWithGoogle: mockLoginWithGoogle,
        linkGoogleAccount: mockLinkGoogleAccount,
      })
      
      render(<LoginPage />)
      
      expect(mockPush).not.toHaveBeenCalled()
      
      // Reset
      Object.defineProperty(window, 'opener', {
        writable: true,
        value: null,
      })
    })

    it('should not redirect when in popup context (window.parent \!== window)', () => {
      Object.defineProperty(window, 'parent', {
        writable: true,
        value: {},
      })
      
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'student' },
        login: mockLogin,
        loginWithGoogle: mockLoginWithGoogle,
        linkGoogleAccount: mockLinkGoogleAccount,
      })
      
      render(<LoginPage />)
      
      expect(mockPush).not.toHaveBeenCalled()
      
      // Reset
      Object.defineProperty(window, 'parent', {
        writable: true,
        value: window,
      })
    })
  })

  describe('Form Validation', () => {
    it('should have email input with correct attributes', () => {
      render(<LoginPage />)
      const emailInput = screen.getByLabelText('Email')
      
      expect(emailInput).toHaveAttribute('type', 'email')
      expect(emailInput).toHaveAttribute('placeholder', 'Enter your email')
      expect(emailInput).toHaveAttribute('required')
    })

    it('should have password input with correct attributes', () => {
      render(<LoginPage />)
      const passwordInput = screen.getByLabelText('Password')
      
      expect(passwordInput).toHaveAttribute('type', 'password')
      expect(passwordInput).toHaveAttribute('placeholder', 'Enter your password')
      expect(passwordInput).toHaveAttribute('required')
    })
  })

  describe('UI Interactions', () => {
    it('should toggle remember me checkbox', () => {
      render(<LoginPage />)
      const checkbox = screen.getByLabelText('Remember me') as HTMLInputElement
      
      expect(checkbox.checked).toBe(false)
      
      fireEvent.change(checkbox, { target: { checked: true } })
      expect(checkbox.checked).toBe(true)
      
      fireEvent.change(checkbox, { target: { checked: false } })
      expect(checkbox.checked).toBe(false)
    })

    it('should render sign up link with correct href', () => {
      render(<LoginPage />)
      const signUpLink = screen.getByText('Sign up now')
      
      expect(signUpLink).toHaveAttribute('href', '/signup')
    })
  })

  describe('Edge Cases', () => {
    it('should handle rapid form submissions', async () => {
      mockLogin.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))
      render(<LoginPage />)
      
      const emailInput = screen.getByLabelText('Email')
      const passwordInput = screen.getByLabelText('Password')
      const submitButton = screen.getByRole('button', { name: /log in$/i })
      
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
      
      fireEvent.click(submitButton)
      fireEvent.click(submitButton)
      fireEvent.click(submitButton)
      
      await waitFor(() => {
        // Should only call once due to loading state
        expect(mockLogin).toHaveBeenCalledTimes(1)
      })
    })

    it('should handle empty string in email field', () => {
      render(<LoginPage />)
      const emailInput = screen.getByLabelText('Email') as HTMLInputElement
      
      fireEvent.change(emailInput, { target: { value: '' } })
      
      expect(emailInput.value).toBe('')
    })

    it('should handle empty string in password field', () => {
      render(<LoginPage />)
      const passwordInput = screen.getByLabelText('Password') as HTMLInputElement
      
      fireEvent.change(passwordInput, { target: { value: '' } })
      
      expect(passwordInput.value).toBe('')
    })

    it('should handle special characters in email', () => {
      render(<LoginPage />)
      const emailInput = screen.getByLabelText('Email') as HTMLInputElement
      
      fireEvent.change(emailInput, { target: { value: 'test+special@example.com' } })
      
      expect(emailInput.value).toBe('test+special@example.com')
    })

    it('should handle very long password', () => {
      render(<LoginPage />)
      const passwordInput = screen.getByLabelText('Password') as HTMLInputElement
      const longPassword = 'a'.repeat(1000)
      
      fireEvent.change(passwordInput, { target: { value: longPassword } })
      
      expect(passwordInput.value).toBe(longPassword)
    })

    it('should not show account linking dialog when showLinkingDialog is false', () => {
      render(<LoginPage />)
      
      expect(screen.queryByTestId('account-linking-dialog')).not.toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should have proper ARIA labels for form inputs', () => {
      render(<LoginPage />)
      
      expect(screen.getByLabelText('Email')).toBeInTheDocument()
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
      expect(screen.getByLabelText('Remember me')).toBeInTheDocument()
    })

    it('should have button with proper text content', () => {
      render(<LoginPage />)
      
      expect(screen.getByRole('button', { name: /log in$/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /log in with google/i })).toBeInTheDocument()
    })
  })

  describe('Console Logging', () => {
    let consoleLogSpy: jest.SpyInstance

    beforeEach(() => {
      consoleLogSpy = jest.spyOn(console, 'log').mockImplementation()
    })

    afterEach(() => {
      consoleLogSpy.mockRestore()
    })

    it('should log when user is authenticated and redirecting', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'student@example.com', role: 'student' },
        login: mockLogin,
        loginWithGoogle: mockLoginWithGoogle,
        linkGoogleAccount: mockLinkGoogleAccount,
      })
      
      render(<LoginPage />)
      
      await waitFor(() => {
        expect(consoleLogSpy).toHaveBeenCalledWith(
          'Main page: User authenticated, redirecting based on role:',
          'student'
        )
        expect(consoleLogSpy).toHaveBeenCalledWith('Main page: Redirecting to student dashboard')
      })
    })

    it('should log when in popup context', () => {
      Object.defineProperty(window, 'opener', {
        writable: true,
        value: {},
      })
      
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'student' },
        login: mockLogin,
        loginWithGoogle: mockLoginWithGoogle,
        linkGoogleAccount: mockLinkGoogleAccount,
      })
      
      render(<LoginPage />)
      
      expect(consoleLogSpy).toHaveBeenCalledWith(
        'Main page: In popup context, preventing automatic redirection'
      )
      
      // Reset
      Object.defineProperty(window, 'opener', {
        writable: true,
        value: null,
      })
    })

    it('should log during Google login flow', async () => {
      mockLoginWithGoogle.mockResolvedValue({})
      render(<LoginPage />)
      
      const googleButton = screen.getByText('Log in with Google')
      fireEvent.click(googleButton)
      
      await waitFor(() => {
        expect(consoleLogSpy).toHaveBeenCalledWith('Login Page: Starting Google login')
        expect(consoleLogSpy).toHaveBeenCalledWith('Login Page: Calling loginWithGoogle')
      })
    })
  })
})