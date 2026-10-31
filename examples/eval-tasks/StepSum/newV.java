public class newV {
    // faster: step by 2 over the even numbers instead of testing every number
    public static double snippet(int n) {
        int i = 0;
        int sum = 0;
        for (i = 0; i <= n; i = i + 2) {
            sum = sum + i;
        }
        return sum;
    }
}
