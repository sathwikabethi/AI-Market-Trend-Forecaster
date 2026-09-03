import { useCallback, useEffect, useMemo, useState } from 'react'
import { getProductTrends, getProducts } from '../lib/api'
import { normalizeProducts, normalizeTrendRows, withMonthLabel } from '../lib/formatters'

export default function useProductTrends() {
    const [products, setProducts] = useState([])
    const [selectedProduct, setSelectedProduct] = useState('')
    const [trendData, setTrendData] = useState([])
    const [isProductsLoading, setIsProductsLoading] = useState(true)
    const [isTrendLoading, setIsTrendLoading] = useState(false)
    const [productError, setProductError] = useState('')
    const [trendError, setTrendError] = useState('')

    useEffect(() => {
        let isActive = true

        const loadProducts = async () => {
            setIsProductsLoading(true)
            try {
                const data = await getProducts()
                if (!isActive) {
                    return
                }
                const normalizedProducts = normalizeProducts(data)
                setProducts(normalizedProducts)
                setSelectedProduct((current) => {
                    if (
                        current &&
                        normalizedProducts.some((product) => product.id === current)
                    ) {
                        return current
                    }
                    return normalizedProducts[0]?.id ?? ''
                })
                setProductError('')
            } catch {
                if (!isActive) {
                    return
                }
                setProducts([])
                setSelectedProduct('')
                setProductError('Unable to load products from backend.')
            } finally {
                if (isActive) {
                    setIsProductsLoading(false)
                }
            }
        }

        loadProducts()
        return () => {
            isActive = false
        }
    }, [])

    const loadTrendData = useCallback(async (productId) => {
        if (!productId) {
            setTrendData([])
            return
        }

        setIsTrendLoading(true)
        try {
            const data = await getProductTrends(productId)
            setTrendData(normalizeTrendRows(data?.trends))
            setTrendError('')
        } catch {
            setTrendData([])
            setTrendError('Unable to load trend data for the selected product.')
        } finally {
            setIsTrendLoading(false)
        }
    }, [])

    useEffect(() => {
        loadTrendData(selectedProduct)
    }, [loadTrendData, selectedProduct])

    const trendChartData = useMemo(() => withMonthLabel(trendData), [trendData])

    return {
        products,
        selectedProduct,
        setSelectedProduct,
        trendData,
        trendChartData,
        isProductsLoading,
        isTrendLoading,
        productError,
        trendError,
        refreshTrendData: () => loadTrendData(selectedProduct),
    }
}
