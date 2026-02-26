/**
 * TypeScript 斐波那契數列計算函式
 * 提供兩種實作方式：遞迴和迭代
 */

/**
 * 遞迴實作斐波那契數列
 * 時間複雜度：O(2^n)
 * 空間複雜度：O(n)
 * @param n - 第 n 個斐波那契數
 * @returns 斐波那契數值
 */
export function fibonacciRecursive(n: number): number {
    if (n < 0) {
        throw new Error('Input must be a non-negative integer');
    }
    
    if (n <= 1) {
        return n;
    }
    
    return fibonacciRecursive(n - 1) + fibonacciRecursive(n - 2);
}

/**
 * 迭代實作斐波那契數列（推薦）
 * 時間複雜度：O(n)
 * 空間複雜度：O(1)
 * @param n - 第 n 個斐波那契數
 * @returns 斐波那契數值
 */
export function fibonacciIterative(n: number): number {
    if (n < 0) {
        throw new Error('Input must be a non-negative integer');
    }
    
    if (n <= 1) {
        return n;
    }
    
    let a = 0;
    let b = 1;
    
    for (let i = 2; i <= n; i++) {
        const temp = a + b;
        a = b;
        b = temp;
    }
    
    return b;
}

/**
 * 使用動態規劃和快取優化的斐波那契數列
 * 時間複雜度：O(n)
 * 空間複雜度：O(n)
 * @param n - 第 n 個斐波那契數
 * @returns 斐波那契數值
 */
export function fibonacciWithMemoization(n: number): number {
    if (n < 0) {
        throw new Error('Input must be a non-negative integer');
    }
    
    const memo: number[] = [0, 1];
    
    function fib(n: number): number {
        if (memo[n] !== undefined) {
            return memo[n];
        }
        
        memo[n] = fib(n - 1) + fib(n - 2);
        return memo[n];
    }
    
    return fib(n);
}

/**
 * 生成斐波那契數列陣列
 * @param length - 數列長度
 * @returns 斐波那契數列陣列
 */
export function generateFibonacciSequence(length: number): number[] {
    if (length < 0) {
        throw new Error('Length must be a non-negative integer');
    }
    
    const sequence: number[] = [];
    
    for (let i = 0; i < length; i++) {
        sequence.push(fibonacciIterative(i));
    }
    
    return sequence;
}

/**
 * 測試函式
 */
function testFibonacci() {
    console.log('=== 斐波那契數列測試 ===');
    
    // 測試前 10 個斐波那契數
    const testCases = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
    
    testCases.forEach(n => {
        console.log(`F(${n}):`);
        console.log(`  遞迴: ${fibonacciRecursive(n)}`);
        console.log(`  迭代: ${fibonacciIterative(n)}`);
        console.log(`  快取: ${fibonacciWithMemoization(n)}`);
    });
    
    // 測試生成數列
    console.log('\n前 10 個斐波那契數列:');
    console.log(generateFibonacciSequence(10));
    
    // 測試錯誤處理
    try {
        fibonacciIterative(-1);
    } catch (error) {
        console.log('\n錯誤處理測試:');
        console.log(`捕獲到錯誤: ${error.message}`);
    }
}

// 如果直接執行此檔案，則執行測試
if (require.main === module) {
    testFibonacci();
}