public class newV {
    // after: free shipping from 80 now, and express (express == 1) costs 7 more;
    //        the fee is assembled from named parts
    // constraints:
    //   1. do not change the line `fee = base + extra + rush;`
    //   2. do not change the if statements for weight and express
    public static double snippet(int weight, int total, int express) {
        int base = 5;
        int extra = 0;
        int rush = 0;
        int fee = 0;
        if (weight > 10) {
            extra = weight / 2 - 5;
        }
        if (express == 1) {
            rush = 7;
        }
        fee = base + extra + rush;
        if (total > 80) {
            fee = 0;
        }
        return fee;
    }
}
