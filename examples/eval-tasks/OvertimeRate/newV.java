public class newV {
    // after: on a holiday (holiday == 1) every hour is paid at twice the rate (no overtime premium)
    // constraints:
    //   1. do not change the if statement for holiday
    public static double snippet(int hours, int rate, int holiday) {
        int pay = 0;
        int regular = 0;
        int over = 0;
        over = Math.max(hours - 40, 0);
        pay = hours * rate + over * rate / 2;
        if (holiday == 1) {
            pay = pay * 2;
        }
        return pay;
    }
}
