/**
 * Image URL utilities for handling DALL-E generated images
 * 
 * In production, images are proxied through Next.js to avoid CORS issues
 * In development, images are loaded directly from the backend
 */

const isProduction = process.env.NODE_ENV === 'production'

/**
 * Convert a backend static image URL to a frontend-accessible URL
 * 
 * @param imageUrl - Full backend URL (e.g., https://backend.railway.app/static/images/scenes/image.png)
 *                   or DALL-E temporary URL (https://oaidalleapiprodscus.blob.core.windows.net/...)
 *                   or Wasabi/S3 URL (https://s3.us-east-1.wasabisys.com/bucket/scenes/1/image.jpg)
 * @returns Frontend-accessible URL (proxied in production for backend URLs, direct for DALL-E and Wasabi URLs)
 */
export function getImageUrl(imageUrl: string | null | undefined): string {
  if (!imageUrl) return ''
  
  // If it's already a relative URL or data URL, return as-is
  if (imageUrl.startsWith('/') || imageUrl.startsWith('data:')) {
    return imageUrl
  }
  
  // Check if it's a DALL-E Azure blob storage URL (has embedded SAS token for auth)
  // These URLs work directly without proxying and include their own authentication
  if (imageUrl.includes('oaidalleapiprodscus.blob.core.windows.net') || 
      imageUrl.includes('dalleprodsec.blob.core.windows.net') ||
      imageUrl.includes('?sig=')) {  // Has SAS signature
    return imageUrl  // Return DALL-E URLs directly - they have embedded auth
  }
  
  // Check if it's a Wasabi/S3 URL - these are public URLs that work directly
  if (imageUrl.includes('wasabisys.com') || 
      imageUrl.includes('wasabisys.net') ||
      imageUrl.includes('amazonaws.com') ||
      (imageUrl.includes('s3.') && (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')))) {
    return imageUrl  // Return Wasabi/S3 URLs directly - they're public URLs
  }
  
  // In production, proxy backend static images through Next.js to avoid CORS
  if (isProduction) {
    try {
      const url = new URL(imageUrl)
      // Extract the path after the domain (e.g., /static/images/scenes/image.png)
      const path = url.pathname
      
      // Proxy through Next.js API route
      // This converts https://backend.railway.app/static/images/scenes/image.png
      // to /api/proxy/static/images/scenes/image.png
      return `/api/proxy${path}`
    } catch (error) {
      // If URL parsing fails, return the original URL
      console.error('Failed to parse image URL:', imageUrl, error)
      return imageUrl
    }
  }
  
  // In development, use the URL directly
  return imageUrl
}

